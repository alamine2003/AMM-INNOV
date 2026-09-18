#!/usr/bin/env bash
# Reconstruit le code « avant » : commit d'origine 6351395, plus la seule instrumentation
# nécessaire à la campagne (commande check_integrity, URL Gmail surchargeable, et le correctif
# GROUP BY du vérificateur). Et la configuration nginx d'origine.
#   ./chaos/make_frozen.sh
set -euo pipefail
cd "$(dirname "$0")/.."
BASE=6351395
rm -rf chaos/frozen-avant-backend && mkdir -p chaos/frozen-avant-backend
git archive "$BASE" backend | tar -x -C chaos/frozen-avant-backend --strip-components=1
mkdir -p chaos/frozen-avant-backend/apps/core/management/commands
cp backend/apps/core/management/__init__.py backend/apps/core/management/commands/__init__.py \
   chaos/frozen-avant-backend/apps/core/management/commands/ 2>/dev/null || true
touch chaos/frozen-avant-backend/apps/core/management/__init__.py
cp backend/apps/core/management/commands/check_integrity.py chaos/frozen-avant-backend/apps/core/management/commands/
python3 - <<'PY'
import pathlib
p = pathlib.Path("chaos/frozen-avant-backend/apps/notifications/backends.py")
s = p.read_text()
s = s.replace("import logging\nimport threading", "import logging\nimport os\nimport threading")
s = s.replace('TOKEN_URL = "https://oauth2.googleapis.com/token"',
              'TOKEN_URL = os.environ.get("GMAIL_TOKEN_URL") or "https://oauth2.googleapis.com/token"')
s = s.replace('SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"',
              'SEND_URL = os.environ.get("GMAIL_SEND_URL") or "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"')
p.write_text(s)
PY
git show "$BASE:docker/nginx.conf" > chaos/frozen-avant-nginx.conf
echo "code « avant » prêt : chaos/frozen-avant-backend, chaos/frozen-avant-nginx.conf"
echo "image Daphne d'origine : git worktree add /tmp/amm-avant $BASE && docker build -f /tmp/amm-avant/docker/backend.Dockerfile --target runtime -t amm-lab-backend:latest /tmp/amm-avant"
