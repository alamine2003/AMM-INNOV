# Backend AMM INNOV (Django 5.1 / DRF)

API REST `/api/v1/`, WebSocket `/ws/` (jeton d'accès dans le sous-protocole `amm.jwt`), Celery (worker + beat), PostgreSQL, Redis.

## Démarrage local (sans Docker Compose)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgres://amm:amm@localhost:5432/amm REDIS_URL=redis://localhost:6379/0
python manage.py migrate
python manage.py seed_demo                      # ceo@amm.local / siege@amm.local / senegal@amm.local — Passw0rd!
python manage.py import_excel "../Dashboard AMM Afrique 18_08_2026 version 2.1.xlsx" --user ceo@amm.local --today 2026-09-04
daphne -b 0.0.0.0 -p 8000 config.asgi:application
celery -A config worker -l info
celery -A config beat -l info
```

Variables : `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DATABASE_URL`, `REDIS_URL`, `ALLOWED_HOSTS`,
`CORS_ALLOWED_ORIGINS`, `EMAIL_URL` (`console://` par défaut, `smtp://user:pass@host:port?tls=1`),
`DEFAULT_FROM_EMAIL`, `FRONTEND_URL`, `MEDIA_ROOT`, `DOCUMENT_MAX_MB`, `TIME_ZONE`,
`GRAFANA_DB_PASSWORD` (rôle `grafana_ro` créé par la migration analytics sur PostgreSQL),
`STORAGE_BACKEND=s3` + `S3_*` en production (settings `prod`).

## Tests et qualité

```bash
pytest -q                 # SQLite par défaut (config.settings.test)
ruff check .
```

Ou via Docker : `docker run --rm -v "$PWD:/app" -w /app python:3.12-slim bash -c "pip install -r requirements-dev.txt && pytest -q"`.

## Commandes utiles

- `seed_demo` : utilisateurs, gammes, 15 pays, règles d'alerte, ~20 AMM de démonstration.
- `seed_alert_rules` : règles globales J-365, J-180, J-90, J-30, J0, DOSSIER.
- `evaluate_alerts [--today AAAA-MM-JJ] [--quiet]` : évaluation des règles (comme le beat nocturne) ; `--quiet` crée les alertes sans notification, pour la première mise en service.
- `import_excel <fichier> [--user email] [--today AAAA-MM-JJ]` : import idempotent du classeur.

## Notes d'implémentation

- Statut/urgence/dates calculés par `apps/amm/services/status.py` à chaque sauvegarde et chaque nuit (00:05 Dakar).
- Les images JPEG/PNG téléversées sont converties en PDF si le paquet optionnel `img2pdf` est installé ; sinon elles sont stockées telles quelles avec leur type MIME réel.
- Le nombre de pages des PDF est calculé par la tâche `generate_document_preview` (pypdf) ; pas de miniature au MVP.
- Schéma OpenAPI : `/api/schema/`, documentation : `/api/docs/`, métriques Prometheus : `/metrics`.
