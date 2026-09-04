# ---------------------------------------------------------------------------
# Image frontend AMM INNOV : build Vite puis nginx servant la SPA et faisant
# reverse proxy vers le backend (API + WebSocket) et Grafana.
# Contexte de build : racine du monorepo.
# ---------------------------------------------------------------------------

# ---------- Stage 1 : build de la SPA ----------
ARG NODE_VERSION=24
FROM node:${NODE_VERSION}-alpine AS build

WORKDIR /app

# VITE_API_BASE est injecté au build (chemin relatif par défaut : nginx proxie /api).
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE} \
    CI=true

COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/ ./
RUN npm run build

# ---------- Stage 2 : nginx ----------
FROM nginx:1.31-alpine AS runtime

RUN rm -f /etc/nginx/conf.d/default.conf
COPY docker/nginx.conf /etc/nginx/conf.d/amm.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost/healthz >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
