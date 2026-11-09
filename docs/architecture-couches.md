# Architecture en couches du backend

AMM GH est un monolithe modulaire : un seul backend Django, découpé en apps. Depuis la 1.1.9,
ces apps sont rangées en trois couches. Le détail et les raisons sont dans la revue
d'architecture du 09/11/2026.

| Couche | Apps | Peut importer |
| --- | --- | --- |
| 1. Socle | `core`, `accounts`, `catalog`, `realtime` | le socle (`core` : rien) |
| 2. Métier | `amm`, `documents`, `alerts`, `deposits`, `notifications` | socle et métier |
| 3. Fonctions transverses | `imports`, `binders`, `analytics` | toutes les couches |

`tests/test_architecture.py` vérifie ces règles à chaque PR. Les écarts qui restent sont listés
dans `KNOWN_EXCEPTIONS` du même fichier, et doivent disparaître dans le palier 1.2.0. Cette
liste ne peut que raccourcir.

## Le socle ne connaît pas le métier

`core` n'importe aucune autre app. Quand il doit faire quelque chose pour une app, c'est l'app
qui se déclare, dans son `hooks.py`, chargé par `AppConfig.ready()` :

| Registre (`apps/core/registry.py`) | Signature | Utilisé par |
| --- | --- | --- |
| `RECOVERY` | `f(now) -> dict[str, int]` | tâche `recover_pending_work` (toutes les 5 min) |
| `INTEGRITY` | `f(options) -> Check \| list[Check]` | `manage.py check_integrity` (chaque nuit) |
| `WORKER_START` | `f() -> dict` | démarrage du worker Celery |
| `PENDING_WORK` | `f() -> bool` | maintien en éveil sur Render gratuit |
| `METRICS` | `f() -> Iterable[Metric]` | `/metrics` (Prometheus) |

Exemple, une nouvelle tâche à rattraper :

```python
# apps/<app>/hooks.py
from apps.core.registry import RECOVERY

@RECOVERY.register
def recover_something(now) -> dict[str, int]:
    ...
    return {"something_republished": count}
```

Les fonctions s'exécutent dans l'ordre des apps de `INSTALLED_APPS`.

## Qui peut faire quoi

Les groupes de rôles (`ALL_ROLES`, `GLOBAL_ROLES`, `CEO_ONLY`, `REGULATORY_ROLES`) et les actions
sensibles sont dans `apps/accounts/roles.py`, et nulle part ailleurs. Le code ne teste pas un
rôle : il demande une action.

- `can(user, Action.BINDER_DELETE_PAGE)` répond vrai ou faux ;
- `ensure_can(user, Action.BINDER_DELETE_PAGE)` (`apps/accounts/permissions.py`) refuse avec un
  403 et le message de l'action.

Ajouter une action, c'est une ligne dans `Action`, une dans `ACTION_ROLES` et une dans
`MESSAGES`. Les vues DRF gardent `RolePermission` (`write_roles`, `action_roles`) avec les mêmes
groupes.

## Conformité des classeurs

`apps/binders/conformity.py` définit un niveau de vérification par classe `Criterion`
(classeur numérique, papier, scan, date et n°). Pour ajouter un niveau, on ajoute une classe à
`CRITERIA` : le résultat et les compteurs de l'étagère suivent sans autre changement.
