#!/usr/bin/env bash
# Installe (ou retire) l'agent de livraison d'AMM GH sur son serveur (1.3.9).
#
#   sudo scripts/serveur/installer_livraison.sh            installe et démarre le minuteur
#   sudo scripts/serveur/installer_livraison.sh --retirer  l'arrête et le retire
#
# Le minuteur systemd lance scripts/serveur/livrer.sh une minute après la fin de chaque passage :
# il demande à GitHub si une version approuvée attend ce serveur, et l'installe.
# Avant : le jeton GitHub, saisi au clavier et rangé dans .env.livraison (jamais dans .env, que
# les conteneurs lisent) :  sudo scripts/serveur/configurer.sh GITHUB_DEPLOY_TOKEN
set -euo pipefail
cd "$(dirname "$0")/../.."
dir=$(pwd)
unit=amm-gh-livraison
systemd=${LIVRAISON_SYSTEMD:-/etc/systemd/system}

log() { echo "[amm-gh] $*" >&2; }
die() { log "ERREUR : $*"; exit 1; }
[ "$(id -u)" = 0 ] || die "à lancer avec sudo"

if [ "${1:-}" = "--retirer" ]; then
  systemctl disable --now "${unit}.timer" >/dev/null 2>&1 || true
  rm -f "${systemd}/${unit}.service" "${systemd}/${unit}.timer"
  systemctl daemon-reload
  log "agent de livraison retiré : les versions s'installent de nouveau à la main"
  exit 0
fi

for tool in git curl python3 flock docker; do
  command -v "$tool" >/dev/null || die "${tool} manque sur ce serveur"
done
[ -f .env ] || die "pas de fichier .env ici (scripts/serveur/preparer_env.sh)"
[ -x scripts/serveur/livrer.sh ] || die "scripts/serveur/livrer.sh absent : installer d'abord la 1.3.9"

# Le script est copié avant d'être lancé : l'installation d'une version remplace le fichier
# d'origine pendant qu'il tourne, et bash lit un script au fil de l'eau. Une copie est gardée
# dans /var/lib/amm-gh-livraison : après un retour à une version d'avant la 1.3.9 (qui n'a pas
# ce script), l'agent continue de tourner.
cat > "${systemd}/${unit}.service" <<EOF
[Unit]
Description=AMM GH : installe les versions approuvées sur GitHub
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=AMM_DIR=${dir}
StateDirectory=${unit}
ExecStart=/bin/sh -c 'if [ -f ${dir}/scripts/serveur/livrer.sh ]; then install -m 700 ${dir}/scripts/serveur/livrer.sh /var/lib/${unit}/livrer.sh; fi && install -m 700 /var/lib/${unit}/livrer.sh /run/${unit}.sh && exec /bin/bash /run/${unit}.sh'
TimeoutStartSec=50min
EOF

cat > "${systemd}/${unit}.timer" <<EOF
[Unit]
Description=AMM GH : regarde chaque minute si une version approuvée attend ce serveur

[Timer]
OnBootSec=3min
OnUnitInactiveSec=1min
Unit=${unit}.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "${unit}.timer" >/dev/null
log "agent de livraison en marche (vérification chaque minute)"
if ! grep -q '^GITHUB_DEPLOY_TOKEN=' .env.livraison 2>/dev/null; then
  log "il attend son jeton : sudo scripts/serveur/configurer.sh GITHUB_DEPLOY_TOKEN"
fi
log "suivi : journalctl -u ${unit} -f    journal : ${dir}/livraisons/journal.log"
