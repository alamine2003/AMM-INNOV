"""Points d'extension du socle : chaque app y déclare ce que `core` doit faire pour elle.

`core` est la couche la plus basse : il ne connaît aucune app métier (principe d'inversion des
dépendances, revue d'architecture du 09/11/2026). Une app qui a du travail à rattraper, des
invariants à contrôler, une reprise à faire au démarrage du worker ou des métriques à publier
s'enregistre ici, depuis son module `hooks.py` chargé par `AppConfig.ready()` :

    from apps.core.registry import RECOVERY

    @RECOVERY.register
    def recover_previews(now) -> dict[str, int]: ...

Les fonctions sont appelées dans l'ordre d'enregistrement, c'est-à-dire l'ordre des apps dans
`INSTALLED_APPS`. Une app du socle ou du métier peut aussi ouvrir ses propres points d'extension
avec `Registry` (plusieurs participants) ou `Provider` (un seul fournisseur) : par exemple
`apps/catalog/extensions.py`, `apps/amm/extensions.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any


class Registry:
    """Liste ordonnée de fonctions, sans doublon (un `ready()` rappelé n'en ajoute pas)."""

    def __init__(self, name: str):
        self.name = name
        self._functions: list[Callable[..., Any]] = []

    def register(self, function: Callable[..., Any]) -> Callable[..., Any]:
        key = (function.__module__, function.__qualname__)
        if all((f.__module__, f.__qualname__) != key for f in self._functions):
            self._functions.append(function)
        return function

    def __iter__(self) -> Iterator[Callable[..., Any]]:
        return iter(list(self._functions))

    def __len__(self) -> int:
        return len(self._functions)


class Provider:
    """Un seul fournisseur pour un service dont le socle a besoin sans le connaître.

    Une app de couche basse déclare le besoin (`COUNTRY_DOCUMENTS = Provider(...)`), une app
    de couche supérieure le remplit (`@COUNTRY_DOCUMENTS.register`). Un appel sans fournisseur
    est une erreur de configuration : l'app qui le remplit n'est pas installée.
    """

    def __init__(self, name: str):
        self.name = name
        self._function: Callable[..., Any] | None = None

    def register(self, function: Callable[..., Any]) -> Callable[..., Any]:
        self._function = function
        return function

    def __call__(self, *args, **kwargs):
        if self._function is None:
            raise RuntimeError(f"Aucun fournisseur pour « {self.name} »")
        return self._function(*args, **kwargs)


# `f(now) -> dict[str, int]` : republie ou clôt le travail resté en plan (tâche
# `recover_pending_work`, toutes les 5 minutes). Les clés forment le rapport.
RECOVERY = Registry("rattrapage du travail en attente")

# `f(options: IntegrityOptions) -> Check | list[Check]` : invariants métier en lecture seule
# (`manage.py check_integrity`, chaque nuit). Voir apps/core/integrity.py.
INTEGRITY = Registry("contrôles d'intégrité")

# `f() -> dict` : reprise au démarrage du worker Celery (analyses coupées par un redémarrage).
WORKER_START = Registry("reprise au démarrage du worker")

# `f() -> bool` : reste-t-il du travail en cours ? (maintien en éveil sur Render gratuit).
PENDING_WORK = Registry("travail en cours")

# `f() -> Iterable[Metric]` : métriques Prometheus propres à une app.
METRICS = Registry("métriques")
