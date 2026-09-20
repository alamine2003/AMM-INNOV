"""Non-régression de la campagne de chaos (docs/audit-resilience) : dépendances Redis/Celery.

Chaque test rejoue en miniature une panne observée sur le laboratoire :
- s03a/s03b : Redis coupé ou figé ⇒ chaque écriture attendait 3 × 5 s, la connexion échouait
  (throttle sur le cache Redis) et un upload restait bloqué sur `task.delay()` ;
- s03c : sous charge, ces attentes tenaient les connexions du pool et faisaient tomber les
  lectures.
"""

import time
from unittest import mock

import pytest
from django.db import transaction
from django.test import override_settings

from apps.core import resilience
from apps.realtime import publisher


@pytest.fixture(autouse=True)
def closed_breakers():
    resilience.REDIS_BREAKER.reset()
    resilience.BROKER_BREAKER.reset()
    yield
    resilience.REDIS_BREAKER.reset()
    resilience.BROKER_BREAKER.reset()


class _HangingLayer:
    """Channel layer dont Redis ne répond plus."""

    def __init__(self, delay=3.0):
        self.delay, self.calls = delay, 0

    async def group_send(self, group, message):
        import asyncio

        self.calls += 1
        await asyncio.sleep(self.delay)


class _BrokenLayer:
    def __init__(self):
        self.calls = 0

    async def group_send(self, group, message):
        self.calls += 1
        raise ConnectionError("Redis indisponible")


# --- configuration : aucun client Redis sans délai borné -----------------------------------


# Les réglages de test remplacent Redis par des équivalents en mémoire : on vérifie donc la
# configuration de production elle-même (config.settings.base).
from config.settings import base as prod  # noqa: E402


def test_redis_clients_have_bounded_timeouts():
    cache_options = prod.CACHES["default"]["OPTIONS"]
    assert 0 < cache_options["socket_timeout"] <= 2
    assert 0 < cache_options["socket_connect_timeout"] <= 2
    host = prod.CHANNEL_LAYERS["default"]["CONFIG"]["hosts"][0]
    # la réception WebSocket bloque 5 s (BZPOPMIN) : le délai socket doit rester au-dessus
    assert host["socket_timeout"] > 5 and host["socket_connect_timeout"] <= 2
    transport = prod.CELERY_BROKER_TRANSPORT_OPTIONS
    assert transport["socket_timeout"] <= 5 and transport["socket_connect_timeout"] <= 2
    assert prod.CELERY_TASK_PUBLISH_RETRY_POLICY["max_retries"] <= 1


@pytest.mark.skipif(
    prod.DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql",
    reason="options libpq : PostgreSQL uniquement",
)
def test_database_calls_are_bounded():
    options = prod.DATABASES["default"]["OPTIONS"]
    assert options["connect_timeout"] <= 10
    for setting in ("statement_timeout", "lock_timeout", "idle_in_transaction_session_timeout"):
        assert f"-c {setting}=" in options["options"]


def test_celery_results_are_not_stored_in_redis():
    """Personne ne lit les résultats : le backend de résultats n'apportait qu'une dépendance
    (abonnement pub/sub) qui bloquait `delay()` indéfiniment quand Redis était figé."""
    assert prod.CELERY_TASK_IGNORE_RESULT is True
    assert not getattr(prod, "CELERY_RESULT_BACKEND", None)


def test_celery_tasks_survive_a_worker_crash():
    assert prod.CELERY_TASK_ACKS_LATE is True
    assert prod.CELERY_TASK_REJECT_ON_WORKER_LOST is True
    assert prod.CELERY_WORKER_PREFETCH_MULTIPLIER == 1


# --- publication temps réel : après commit, bornée, disjoncteur ---------------------------


@pytest.mark.django_db
def test_publish_waits_for_commit(django_capture_on_commit_callbacks):
    layer = _BrokenLayer()
    with mock.patch.object(publisher, "get_channel_layer", return_value=layer):
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            with transaction.atomic():
                publisher.publish("global", {"type": "x"})
                assert layer.calls == 0  # rien ne part tant que la transaction tient ses verrous
        assert len(callbacks) == 1


@pytest.mark.django_db(transaction=True)  # vrais commits : la publication part après commit
def test_publish_is_bounded_when_redis_hangs():
    layer = _HangingLayer(delay=3.0)
    with mock.patch.object(publisher, "get_channel_layer", return_value=layer):
        started = time.monotonic()
        publisher.publish("global", {"type": "x"})
        assert time.monotonic() - started < publisher.PUBLISH_TIMEOUT + 0.5


@pytest.mark.django_db(transaction=True)  # vrais commits : la publication part après commit
def test_breaker_skips_redis_after_a_failure():
    layer = _BrokenLayer()
    with mock.patch.object(publisher, "get_channel_layer", return_value=layer):
        publisher.publish("global", {"type": "x"})
        for _ in range(5):
            publisher.publish("global", {"type": "x"})
    assert layer.calls == 1  # une seule tentative, puis le disjoncteur court-circuite
    assert resilience.REDIS_BREAKER.state == "open"


def test_breaker_half_opens_after_cooldown():
    breaker = resilience.CircuitBreaker("test", cooldown=0.1)
    breaker.failure()
    assert not breaker.allow()
    time.sleep(0.15)
    assert breaker.allow()  # un essai
    assert not breaker.allow()  # un seul à la fois
    breaker.success()
    assert breaker.allow() and breaker.state == "closed"


@pytest.mark.django_db(transaction=True)  # vrais commits : la publication part après commit
def test_amm_write_is_fast_when_realtime_is_down(ceo_client, make_amm):
    amm = make_amm()
    layer = _HangingLayer(delay=5.0)
    with mock.patch.object(publisher, "get_channel_layer", return_value=layer):
        started = time.monotonic()
        response = ceo_client.patch(f"/api/v1/amms/{amm.pk}", {"notes": "x"}, format="json")
        elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert elapsed < publisher.PUBLISH_TIMEOUT + 1.0  # et non 3 publications × 5 s


# --- connexion sans cache Redis ----------------------------------------------------------------


@pytest.mark.django_db
def test_login_works_when_the_cache_is_unavailable(users, anon_client):
    import secrets

    from django.core.cache import cache

    credential = secrets.token_urlsafe(16)  # tiré au hasard : aucun secret dans le dépôt
    users["ceo"].set_password(credential)
    users["ceo"].save(update_fields=["password"])
    with mock.patch.object(cache, "get", side_effect=ConnectionError("down")), mock.patch.object(
        cache, "set", side_effect=ConnectionError("down")
    ):
        response = anon_client.post(
            "/api/v1/auth/login", {"email": users["ceo"].email, "password": credential}
        )
    assert response.status_code == 200


@pytest.mark.django_db
def test_login_throttle_still_applies_in_fallback(users, anon_client):
    """Repli local : la protection anti force brute reste active, par processus."""
    from django.core.cache import cache

    from apps.accounts.views import LoginThrottle

    LoginThrottle.THROTTLE_RATES = {"login": "3/min", "login_email": "100/min"}
    try:
        down = ConnectionError("down")
        with mock.patch.object(cache, "get", side_effect=down), mock.patch.object(
            cache, "set", side_effect=down
        ):
            codes = [
                anon_client.post(
                    "/api/v1/auth/login", {"email": "ceo@test.local", "password": "faux"}
                ).status_code
                for _ in range(5)
            ]
    finally:
        del LoginThrottle.THROTTLE_RATES
    assert 429 in codes


# --- publication de tâches : jamais d'échec après commit -----------------------------------


@pytest.mark.django_db(transaction=True)  # vrais commits : on_commit s'exécute dans la requête
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_enqueue_failure_does_not_fail_a_committed_upload(ceo_client, make_amm):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.documents.models import Document
    from apps.documents.tasks import generate_document_preview
    from tests.conftest import MINIMAL_PDF

    amm = make_amm()
    upload = SimpleUploadedFile(
        "scan.pdf", MINIMAL_PDF + b"%enqueue", content_type="application/pdf"
    )
    with mock.patch.object(
        generate_document_preview, "delay", side_effect=ConnectionError("broker down")
    ):
        response = ceo_client.post(
            f"/api/v1/amms/{amm.pk}/documents", {"file": upload, "kind": "AMM"}, format="multipart"
        )
    assert response.status_code == 201
    assert Document.objects.filter(amm=amm).count() == 1


# --- sondes de santé -------------------------------------------------------------------------


@pytest.mark.django_db
def test_liveness_does_not_touch_dependencies(anon_client):
    cursor = "django.db.backends.base.base.BaseDatabaseWrapper.cursor"
    with mock.patch(cursor, side_effect=Exception):
        response = anon_client.get("/api/v1/health/live")
    assert response.status_code == 200


@pytest.mark.django_db
def test_readiness_reports_redis_quickly(anon_client):
    import redis

    with mock.patch.object(redis.Redis, "ping", side_effect=ConnectionError):
        started = time.monotonic()
        response = anon_client.get("/api/v1/health")
    assert time.monotonic() - started < 2
    assert response.status_code == 200 and response.json()["redis"] is False


@pytest.mark.django_db
def test_database_saturation_returns_a_json_503(ceo_client):
    """Pool épuisé (s02e) : 503 JSON avec Retry-After, et non une page HTML 500."""
    from django.db import OperationalError

    from apps.amm.views import AmmViewSet

    pool_timeout = OperationalError("couldn't get a connection after 10.00 sec")
    with mock.patch.object(AmmViewSet, "list", side_effect=pool_timeout):
        response = ceo_client.get("/api/v1/amms")
    assert response.status_code == 503
    assert response["Retry-After"] == "5"
    assert "réessayez" in response.json()["detail"]


@pytest.mark.django_db
def test_readiness_answers_503_quickly_when_the_database_is_down(anon_client):
    from apps.accounts import views

    with mock.patch.object(views, "database_reachable", return_value=False):
        response = anon_client.get("/api/v1/health")
    assert response.status_code == 503 and response.json()["database"] is False


@pytest.mark.django_db
def test_readiness_uses_django_connection_parameters():
    """sslmode et autres OPTIONS de DATABASES doivent atteindre la connexion de la sonde."""
    from apps.accounts import views

    params = {"dbname": "amm", "sslmode": "verify-full", "options": "-c lock_timeout=1"}
    with mock.patch.object(views.connection, "vendor", "postgresql"), mock.patch.object(
        views.connection, "get_connection_params", return_value=dict(params)
    ), mock.patch("psycopg.connect") as connect:
        assert views.database_reachable() is True
    kwargs = connect.call_args.kwargs
    assert kwargs["sslmode"] == "verify-full" and kwargs["connect_timeout"] == 2
    assert "lock_timeout=1" in kwargs["options"] and "statement_timeout=2000" in kwargs["options"]


@pytest.mark.django_db(transaction=True)
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_task_publication_is_attempted_even_when_realtime_breaker_is_open(ceo_client, make_amm):
    """Un délai du temps réel ne doit pas faire sauter la publication d'une tâche."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.documents.tasks import generate_document_preview
    from tests.conftest import MINIMAL_PDF

    resilience.REDIS_BREAKER.failure()
    upload = SimpleUploadedFile("scan.pdf", MINIMAL_PDF + b"%breaker")
    url = f"/api/v1/amms/{make_amm().pk}/documents"
    with mock.patch.object(generate_document_preview, "delay") as delay:
        response = ceo_client.post(url, {"file": upload, "kind": "AMM"}, format="multipart")
    assert response.status_code == 201
    delay.assert_called_once()


@pytest.mark.django_db
def test_upload_when_storage_is_down_is_a_clean_503(ceo_client, make_amm):
    """Stockage injoignable pendant un upload (s10a) : 503 explicite, rien d'enregistré."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.db.models.fields.files import FieldFile

    from apps.documents.models import Document
    from tests.conftest import MINIMAL_PDF

    amm = make_amm()
    upload = SimpleUploadedFile("scan.pdf", MINIMAL_PDF + b"%s3down")
    with mock.patch.object(FieldFile, "save", side_effect=ConnectionError("S3 down")):
        response = ceo_client.post(
            f"/api/v1/amms/{amm.pk}/documents", {"file": upload, "kind": "AMM"}, format="multipart"
        )
    assert response.status_code == 503
    assert not Document.objects.filter(amm=amm).exists()


@pytest.mark.django_db(transaction=True)
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_broker_down_costs_one_attempt_then_is_skipped(ceo_client, make_amm):
    """Broker en panne : le premier upload paie une tentative, les suivants ne l'attendent plus."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.documents.tasks import generate_document_preview
    from tests.conftest import MINIMAL_PDF

    amm = make_amm()
    url = f"/api/v1/amms/{amm.pk}/documents"
    broken = mock.patch.object(generate_document_preview, "delay", side_effect=ConnectionError)
    with broken as delay:
        for i in range(3):
            upload = SimpleUploadedFile(f"s{i}.pdf", MINIMAL_PDF + f"%broker{i}".encode())
            response = ceo_client.post(url, {"file": upload, "kind": "AMM"}, format="multipart")
            assert response.status_code == 201
    assert delay.call_count == 1


def test_archive_blocks_are_pulled_one_at_a_time():
    """s08 rejoué : sous ASGI, Django lisait tout l'itérateur synchrone avant d'envoyer. Le flux
    asynchrone ne tire que le bloc demandé, et referme la source si le client s'en va."""
    import asyncio

    from apps.documents.services.archive import aiter_blocks

    pulled, closed = [], []

    def source():
        try:
            for i in range(100):
                pulled.append(i)
                yield b"x" * 10
        finally:
            closed.append(True)

    async def client_reads_two_blocks_then_leaves():
        blocks = aiter_blocks(b"first", source())
        received = [await anext(blocks), await anext(blocks)]
        await blocks.aclose()
        return received

    assert asyncio.run(client_reads_two_blocks_then_leaves()) == [b"first", b"x" * 10]
    assert pulled == [0]
    assert closed == [True]


@pytest.mark.django_db(transaction=True)
def test_archive_is_streamed_asynchronously_under_asgi(users, make_amm):
    """Par le client ASGI de Django : la réponse est un flux asynchrone, et le ZIP est complet."""
    import asyncio
    import io
    import zipfile

    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.test import AsyncClient
    from rest_framework_simplejwt.tokens import RefreshToken

    from tests.conftest import MINIMAL_PDF, client_for

    amm = make_amm()
    url = f"/api/v1/amms/{amm.pk}/documents"
    uploader = client_for(users["ceo"])
    for i in range(2):
        upload = SimpleUploadedFile(f"s{i}.pdf", MINIMAL_PDF + f"%asgi{i}".encode())
        response = uploader.post(url, {"file": upload, "kind": "AUTRE"}, format="multipart")
        assert response.status_code == 201
    headers = {"Authorization": f"Bearer {RefreshToken.for_user(users['ceo']).access_token}"}

    async def download():
        response = await AsyncClient().get(f"{url}/archive.zip", headers=headers)
        assert response.status_code == 200 and response.is_async
        return b"".join([chunk async for chunk in response.streaming_content])

    names = zipfile.ZipFile(io.BytesIO(asyncio.run(download()))).namelist()
    assert len(names) == 2
