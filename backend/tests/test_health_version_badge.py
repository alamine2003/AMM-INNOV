"""GET /api/v1/health : clé `version`, sonde Redis bornée et schéma OpenAPI typé.

Endpoint public, en lecture seule, sans donnée pays : la matrice habituelle (périmètre pays,
rôle insuffisant) ne s'applique pas. `test_health_ignores_authentication_header` et
`test_health_rejects_post` en tiennent lieu.
"""

import threading
import time

import pytest
from django.db.utils import OperationalError
from drf_spectacular.generators import SchemaGenerator

from apps.accounts import views as health_views
from config.settings.base import clean_app_version

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_redis_health_check_state():
    """Le contrôle Redis est mutualisé par un exécuteur de module unique (un seul worker) : on
    s'assure qu'aucun contrôle d'un test précédent (par ex. un ping délibérément lent, cycle-2 F1)
    ne traîne avant le suivant, pour ne pas fausser le regroupement des sondes ni sa mesure de
    délai.
    """

    def _drain() -> None:
        future = health_views._redis_check_future
        if future is not None:
            try:
                future.result(timeout=10)
            except Exception:
                pass  # le résultat importe peu ici, seul l'achèvement compte
        health_views._redis_check_future = None

    _drain()
    yield
    _drain()


def test_health_body_has_exactly_four_keys(anon_client, settings, django_assert_max_num_queries):
    # Au plus une requête : la sonde reste bon marché. Sur PostgreSQL elle n'en fait aucune par la
    # connexion Django, car elle ouvre une connexion directe hors pool (campagne de chaos s02a) ;
    # sur SQLite elle passe par le curseur habituel.
    with django_assert_max_num_queries(1):
        response = anon_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "database", "redis", "version"}
    assert body["status"] == "ok"
    assert body["database"] is True
    assert isinstance(body["redis"], bool)
    assert body["version"] == settings.APP_VERSION


def test_health_exposes_configured_version(anon_client, settings):
    settings.APP_VERSION = "1.4.2-rc.1+sha.abc1234"
    response = anon_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["version"] == "1.4.2-rc.1+sha.abc1234"


def test_health_ignores_authentication_header(anon_client):
    response = anon_client.get("/api/v1/health", HTTP_AUTHORIZATION="Bearer invalide")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_degraded_when_database_down(anon_client, monkeypatch):
    class _BrokenConnection:
        def cursor(self):
            raise OperationalError("simulated outage")

    # Un objet de substitution : la vraie connexion (utilisée par le test lui-même via l'ORM)
    # n'est jamais touchée.
    monkeypatch.setattr("apps.accounts.views.connection", _BrokenConnection())

    response = anon_client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert set(body) == {"status", "database", "redis", "version"}
    assert body["status"] == "degraded"
    assert body["database"] is False
    assert "exception" not in response.content.decode().lower()
    assert "traceback" not in response.content.decode().lower()


def test_health_redis_down_keeps_ok_200(anon_client, monkeypatch):
    class _FailingClient:
        def ping(self):
            raise ConnectionError("simulated outage")

        def close(self):
            pass

    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **k: _FailingClient())

    response = anon_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["redis"] is False


@pytest.mark.parametrize("ping_raises", [False, True], ids=["ping_ok", "ping_fails"])
def test_health_redis_ping_is_bounded_and_closed(anon_client, monkeypatch, ping_raises):
    calls: dict = {}

    class _FakeClient:
        def __init__(self):
            self.closed = 0

        def ping(self):
            if ping_raises:
                raise ConnectionError("simulated outage")
            return True

        def close(self):
            self.closed += 1

    fake_client = _FakeClient()

    def fake_from_url(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        return fake_client

    monkeypatch.setattr("redis.Redis.from_url", fake_from_url)

    response = anon_client.get("/api/v1/health")
    assert response.status_code == 200
    assert calls["kwargs"]["socket_connect_timeout"] == 1
    assert calls["kwargs"]["socket_timeout"] == 1
    assert fake_client.closed == 1


def test_health_redis_check_bounded_by_global_timeout(anon_client, monkeypatch):
    """Cycle-2 F1 : un contrôle Redis plus lent que le délai global (ex. résolution DNS non bornée
    par redis-py) ne doit jamais faire attendre la réponse jusqu'à sa fin ; `redis: false` et une
    durée de réponse bornée par le délai patché, très en-deçà des ~4 s mesurés en simulation."""
    monkeypatch.setattr(health_views, "HEALTH_REDIS_CHECK_TIMEOUT", 0.05)

    class _SlowClient:
        def ping(self):
            time.sleep(0.3)  # simule une résolution DNS ou un ping plus lent que le délai global
            return True

        def close(self):
            pass

    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **k: _SlowClient())

    started = time.monotonic()
    response = anon_client.get("/api/v1/health")
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["redis"] is False
    # Bien en-deçà des ~4 s de la panne réelle (S3) : la réponse ne dépend pas de la durée du ping.
    assert elapsed < 1.0


def test_health_redis_check_coalesces_concurrent_probes(monkeypatch):
    """Cycle-2 F1 : plusieurs contrôles concurrents pendant un contrôle en cours attendent CE
    contrôle (même future) au lieu d'en soumettre un autre : un seul appel à `from_url`, toutes les
    sondes reçoivent le même résultat. Sous ASGI, une sonde en vol ne doit pas faire répondre
    `redis: false` à tort à une autre requête pendant que Redis va bien."""
    monkeypatch.setattr(health_views, "HEALTH_REDIS_CHECK_TIMEOUT", 2.0)
    calls: list[str] = []
    ping_started = threading.Event()
    release_ping = threading.Event()

    class _SlowClient:
        def ping(self):
            ping_started.set()
            assert release_ping.wait(timeout=5), "le test n'a jamais libéré le ping simulé"
            return True

        def close(self):
            pass

    def fake_from_url(url, **kwargs):
        calls.append(url)
        return _SlowClient()

    monkeypatch.setattr("redis.Redis.from_url", fake_from_url)

    results: list[bool] = []
    results_lock = threading.Lock()

    def probe() -> None:
        result = health_views._check_redis_bounded()
        with results_lock:
            results.append(result)

    first = threading.Thread(target=probe)
    first.start()
    assert ping_started.wait(timeout=2), "le premier contrôle n'a pas démarré"

    others = [threading.Thread(target=probe) for _ in range(3)]
    for thread in others:
        thread.start()

    release_ping.set()
    first.join(timeout=5)
    for thread in others:
        thread.join(timeout=5)

    assert calls == [health_views.settings.REDIS_URL]  # un seul appel à from_url
    assert results == [True, True, True, True]


def test_health_redis_check_fast_ping_returns_true(anon_client, monkeypatch):
    """Pas de régression : un ping Redis rapide continue de donner `redis: true`."""

    class _FastClient:
        def ping(self):
            return True

        def close(self):
            pass

    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **k: _FastClient())

    response = anon_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["redis"] is True


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "dev"),
        ("", "dev"),
        ("   ", "dev"),
        ("  1.4.2\n", "1.4.2"),
        ("1.4.2-rc.1+sha.abc1234", "1.4.2-rc.1+sha.abc1234"),
        ("a" * 40, "a" * 40),
        ("a" * 64, "a" * 64),
        ("a" * 65, "dev"),
        ("1.0 beta", "dev"),
        ("<script>alert(1)</script>", "dev"),
        ("1.0\n2", "dev"),
        (".1", "dev"),
        ("-x", "dev"),
    ],
)
def test_clean_app_version(raw, expected):
    assert clean_app_version(raw) == expected


def test_health_schema_is_typed():
    generator = SchemaGenerator()
    schema = generator.get_schema(request=None, public=True)

    health_get = schema["paths"]["/api/v1/health/"]["get"]
    for code in ("200", "503"):
        ref = health_get["responses"][code]["content"]["application/json"]["schema"]["$ref"]
        assert ref == "#/components/schemas/Health"

    health_schema = schema["components"]["schemas"]["Health"]
    assert set(health_schema["required"]) == {"status", "database", "redis", "version"}
    assert health_schema["properties"]["status"]["$ref"] == "#/components/schemas/HealthStatusEnum"

    enum_schema = schema["components"]["schemas"]["HealthStatusEnum"]
    assert set(enum_schema["enum"]) == {"ok", "degraded"}


def test_health_rejects_post(anon_client):
    assert anon_client.post("/api/v1/health").status_code == 405
