# ---------------------------------------------------------------------------
# Image backend AMM INNOV (Django + Daphne + Celery)
# Contexte de build : racine du monorepo (docker compose build / CI).
# ---------------------------------------------------------------------------

# ---------- Stage 1 : construction du virtualenv ----------
FROM python:3.14-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip wheel && pip install -r /tmp/requirements.txt

# ---------- Stage 2 : image d'exécution ----------
FROM python:3.14-slim AS runtime

ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    MEDIA_ROOT=/app/media \
    TZ=Africa/Dakar

# libpq5 : client PostgreSQL pour psycopg ; curl : healthcheck ; tzdata : fuseau Dakar
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --shell /bin/bash app

COPY --from=builder /opt/venv /opt/venv

# Scripts utilitaires hors de /app : ils restent disponibles quand ./backend est monté en volume.
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY --chmod=755 scripts/wait-for.py /usr/local/bin/wait-for.py

WORKDIR /app
COPY --chown=app:app backend/ /app/
RUN mkdir -p /app/media /app/staticfiles && chown -R app:app /app/media /app/staticfiles

USER app

EXPOSE 8000

# Sonde de santé de l'API (vérifie base et Redis)
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health >/dev/null 2>&1 || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
