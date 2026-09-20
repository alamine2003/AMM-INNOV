"""Compléments unitaires à `test_health_version_badge.py` (testeur-unitaire, cycle 1, 2 et 3).

Ne duplique pas les tests déjà livrés par dev-backend : borne de longueur 63 (au lieu de
40/64/65 seulement), caractères Unicode, caractère spécial en tête bien qu'autorisé en position
suivante, tabulation interne vs. tabulation de bord, et **ordre exact** des 4 clés du corps JSON
(le contrat dit « ces 4 clés, dans cet ordre », jamais vérifié par un simple `set(body) == {...}`).

Cycle 2 (F1) : `close()` du client Redis qui lève — vérifie que la sonde répond quand même et
que le logger de module journalise désormais en DEBUG (plus de `except Exception: pass`).

Cycle 3 : vérification du correctif F1 (exécuteur de module à un seul worker, délai global
`HEALTH_REDIS_CHECK_TIMEOUT`, future partagée sous verrou). `test_health_version_badge.py` couvre
déjà le dépassement de délai côté HTTP et le regroupement des sondes *simultanées* ; ce fichier
couvre la suite *séquentielle* d'appels à `_check_redis_bounded()` : une exception (ni délai ni
succès) ne doit pas se substituer indéfiniment à un contrôle frais, une future dépassée qui se
termine en arrière-plan ne doit pas empêcher la sonde suivante de relancer un contrôle, un contrôle
terminé (même en succès) ne doit jamais servir de cache, et le délai global doit aussi s'appliquer
quand c'est `close()` qui bloque (pas seulement `ping()`).
"""

import logging
import threading
import time

import pytest
from django.db.utils import OperationalError

from apps.accounts import views as health_views
from config.settings.base import clean_app_version

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_redis_health_check_state():
    """Même nécessité que dans `test_health_version_badge.py` : l'exécuteur et sa future de module
    sont un état **partagé par tout le processus pytest**, donc aussi par les autres fichiers de
    test exécutés dans la même session (SQLite). On draine tout contrôle laissé en vol avant et
    après chaque test pour ne jamais laisser un thread de l'exécuteur bloqué entre deux tests, et
    pour que chaque test parte d'un état propre (`_redis_check_future is None`).
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


def test_health_body_key_order_nominal(anon_client):
    """CA1 : « exactement ces 4 clés, dans cet ordre » — un `set()` ne suffit pas à le prouver."""
    response = anon_client.get("/api/v1/health")
    assert response.status_code == 200
    raw = response.content.decode()
    positions = [raw.index(f'"{key}"') for key in ("status", "database", "redis", "version")]
    assert positions == sorted(positions), raw


def test_health_body_key_order_degraded(anon_client, monkeypatch):
    """Même exigence d'ordre côté 503 (CA3)."""

    class _BrokenConnection:
        def cursor(self):
            raise OperationalError("simulated outage")

    monkeypatch.setattr("apps.accounts.views.connection", _BrokenConnection())

    response = anon_client.get("/api/v1/health")
    assert response.status_code == 503
    raw = response.content.decode()
    positions = [raw.index(f'"{key}"') for key in ("status", "database", "redis", "version")]
    assert positions == sorted(positions), raw


def test_health_redis_close_failure_is_logged_at_debug(anon_client, monkeypatch, caplog):
    """F1 (cycle 1) : `close()` qui lève ne doit plus être avalé silencieusement.

    La sonde répond quand même 200 avec `database: true` et les 4 clés attendues, et le logger
    de module `apps.accounts.views` reçoit un enregistrement DEBUG (`exc_info` renseigné) au lieu
    du `except Exception: pass` d'origine (constat bandit B110, cycle 1).
    """

    class _ClosingFailsClient:
        def ping(self):
            return True

        def close(self):
            raise RuntimeError("simulated close failure")

    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **k: _ClosingFailsClient())

    with caplog.at_level(logging.DEBUG, logger="apps.accounts.views"):
        response = anon_client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "database", "redis", "version"}
    assert body["status"] == "ok"
    assert body["database"] is True
    # Le ping a réussi avant l'échec de close() : le except externe ne doit pas faire passer
    # redis à false rétroactivement (comportement voulu par le correctif F1).
    assert body["redis"] is True

    debug_records = [
        r for r in caplog.records if r.name == "apps.accounts.views" and r.levelno == logging.DEBUG
    ]
    assert len(debug_records) == 1, caplog.records
    record = debug_records[0]
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1], RuntimeError)


def test_health_redis_check_exception_then_next_probe_is_fresh_not_stuck(monkeypatch):
    """Cycle 3 : une exception levée pendant le contrôle (ni délai dépassé, ni succès — ici avant
    même `ping()`, dans `from_url`) donne `redis: false`, et la sonde SUIVANTE relance bien un
    contrôle frais : elle ne réutilise pas indéfiniment ce résultat en échec. Dès que Redis répond
    de nouveau, `redis` redevient `true`."""
    monkeypatch.setattr(health_views, "HEALTH_REDIS_CHECK_TIMEOUT", 1.5)
    calls: list[str] = []

    class _OkClient:
        def ping(self):
            return True

        def close(self):
            pass

    def fake_from_url(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            # Panne pendant la résolution/connexion elle-même, pas un ping qui échoue proprement
            # (déjà couvert par test_health_redis_ping_is_bounded_and_closed[ping_fails]).
            raise RuntimeError("panne simulée avant le ping")
        return _OkClient()

    monkeypatch.setattr("redis.Redis.from_url", fake_from_url)

    first = health_views._check_redis_bounded()
    assert first is False

    # Le contrôle raté est bien terminé (Future.exception() attend la fin sans relever l'exception,
    # contrairement à .result()) avant de soumettre la sonde suivante : exécuteur à un seul worker.
    failed_future = health_views._redis_check_future
    assert failed_future is not None
    assert isinstance(failed_future.exception(timeout=5), RuntimeError)

    second = health_views._check_redis_bounded()
    assert second is True
    assert len(calls) == 2  # une nouvelle future a bien été soumise, pas de réutilisation
    assert health_views._redis_check_future is not failed_future


def test_health_redis_check_next_probe_is_fresh_after_timed_out_check_finishes(monkeypatch):
    """Cycle 3 : après un contrôle qui a dépassé le délai global puis s'est terminé en arrière-plan
    (Redis a fini par répondre, mais trop tard pour la 1re sonde), la sonde SUIVANTE relance un
    contrôle frais plutôt que de réutiliser cette future dépassée — et si Redis est revenu, `redis`
    redevient `true` sans attendre le prochain cycle du cache DNS négatif (cycle-2 F1)."""
    monkeypatch.setattr(health_views, "HEALTH_REDIS_CHECK_TIMEOUT", 0.05)
    calls: list[str] = []
    ping_started = threading.Event()
    release_ping = threading.Event()

    class _SlowThenFastClient:
        def __init__(self, blocking: bool):
            self._blocking = blocking

        def ping(self):
            if self._blocking:
                ping_started.set()
                assert release_ping.wait(timeout=5), "le test n'a jamais libéré le ping simulé"
            return True

        def close(self):
            pass

    def fake_from_url(url, **kwargs):
        blocking = len(calls) == 0
        calls.append(url)
        return _SlowThenFastClient(blocking)

    monkeypatch.setattr("redis.Redis.from_url", fake_from_url)

    first = health_views._check_redis_bounded()
    assert first is False  # délai (0,05 s) dépassé pendant que le ping simulé était bloqué
    assert ping_started.wait(timeout=2), "le premier contrôle n'a pas démarré"

    # Le contrôle en vol se termine enfin en arrière-plan (Redis répondait) : son succès ne doit
    # pas être réutilisé comme cache par la sonde suivante — il doit juste être ignoré.
    release_ping.set()
    timed_out_future = health_views._redis_check_future
    assert timed_out_future is not None
    assert timed_out_future.result(timeout=5) is True

    # Délai remis à une valeur confortable : ce qui est vérifié ici, c'est la fraîcheur de la sonde
    # suivante, pas à nouveau le respect du délai (déjà couvert par ailleurs).
    monkeypatch.setattr(health_views, "HEALTH_REDIS_CHECK_TIMEOUT", 1.5)
    second = health_views._check_redis_bounded()
    assert second is True  # Redis répond de nouveau, via un contrôle frais
    assert len(calls) == 2  # 2e appel à from_url : une vraie nouvelle sonde, pas la future dépassée
    assert health_views._redis_check_future is not timed_out_future


def test_health_redis_check_completed_success_not_reused_as_cache(monkeypatch):
    """Cycle 3 : un contrôle terminé n'est jamais réutilisé comme cache pour les sondes suivantes,
    même quand il s'est terminé avec succès — chaque sonde après achèvement du précédent contrôle
    en relance un nouveau plutôt que de renvoyer le dernier résultat connu."""
    monkeypatch.setattr(health_views, "HEALTH_REDIS_CHECK_TIMEOUT", 1.5)
    calls: list[str] = []

    class _OkClient:
        def ping(self):
            return True

        def close(self):
            pass

    class _DownClient:
        def ping(self):
            raise ConnectionError("simulated outage")

        def close(self):
            pass

    def fake_from_url(url, **kwargs):
        calls.append(url)
        return _OkClient() if len(calls) == 1 else _DownClient()

    monkeypatch.setattr("redis.Redis.from_url", fake_from_url)

    first = health_views._check_redis_bounded()
    assert first is True

    completed_future = health_views._redis_check_future
    assert completed_future is not None
    assert completed_future.result(timeout=5) is True

    second = health_views._check_redis_bounded()
    assert second is False  # pas le `True` du 1er contrôle réutilisé : Redis est tombé entre-temps
    assert len(calls) == 2


def test_health_redis_check_bounded_when_close_blocks(anon_client, monkeypatch):
    """Cycle 3 : le commentaire de module (views.py:153) promet un délai global sur l'ensemble
    résolution+connexion+PING+fermeture, pas seulement sur le PING. Un `close()` qui bloque après
    un ping réussi ne doit donc pas non plus faire dépasser le délai global à la réponse HTTP —
    seul `ping()` était couvert jusqu'ici (test_health_redis_check_bounded_by_global_timeout)."""
    monkeypatch.setattr(health_views, "HEALTH_REDIS_CHECK_TIMEOUT", 0.05)

    class _SlowCloseClient:
        def ping(self):
            return True

        def close(self):
            # Bloque après un ping réussi ; se termine seul, aucun thread ne reste bloqué.
            time.sleep(0.3)

    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **k: _SlowCloseClient())

    started = time.monotonic()
    response = anon_client.get("/api/v1/health")
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # close() bloquant fait aussi dépasser le délai global, comme ping().
    assert body["redis"] is False
    # Bien en-deçà des 0,3 s de close() : la réponse ne dépend pas de la durée de close().
    assert elapsed < 0.2


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Borne 63 (la borne 64 valide et 65 rejetée sont déjà couvertes par
        # test_health_version_badge.py::test_clean_app_version).
        ("a" * 63, "a" * 63),
        # Unicode : hors de [0-9A-Za-z._+-], quelle que soit la position.
        ("café-1.4.2", "dev"),
        ("1.4.2é", "dev"),
        ("１.4.2", "dev"),  # chiffre unicode pleine chasse '１', pas un ASCII [0-9]
        ("\U0001f600" + "1.4.2", "dev"),  # emoji en tête
        # Caractère spécial en tête : autorisé en position suivante (._+-) mais pas en premier
        # caractère (le regex impose [0-9A-Za-z] en tête).
        ("+1.4.2", "dev"),
        ("_1.4.2", "dev"),
        # Tabulation interne (non un espace de bord) vs. tabulations de bord (retirées par strip()).
        ("1.4\t.2", "dev"),
        ("\t1.4.2\t", "1.4.2"),
    ],
)
def test_clean_app_version_boundaries(raw, expected):
    assert clean_app_version(raw) == expected
