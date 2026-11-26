# Palier 1.4.0 : livraison continue, validation, retour arrière

La 1.4.0 clôt le cycle 1.3 (le premier sur le Serveur 01 Stellarix) et rend opérationnelle la
chaîne de livraison posée en 1.3.9 : de l'étiquette à la production, avec l'approbation de
Mohamed, sans commande sur le serveur. Le contenu est dans `CHANGELOG.md`. Ce document répond aux
exigences d'un palier (`docs/versionnement.md`).

## Le cycle 1.3 en bref

| Version | Apport |
| --- | --- |
| 1.3.0 | sauvegardes chiffrées, relues, copiées hors machine ; bascule Render → Stellarix (17/11) |
| 1.3.1 | interface en anglais (bouton FR / EN) |
| 1.3.2 | corbeille : plus d'erreur 500 sur une fiche rangée par un import de dossier |
| 1.3.3 | classeur numérique : fin des fiches qui tremblent ou se coupent |
| 1.3.4 | mémoire de l'API : scans lus bloc par bloc, réglages de l'allocateur |
| 1.3.5 | scans servis par nginx depuis le stockage (l'API ne les porte plus) |
| 1.3.6 à 1.3.8 | Congo : le numéro d'AMM est le Code de l'article 2, périodes au 28 février, relecture prudente du classeur |
| 1.3.9 | workflow « Livraison » et agent de livraison du serveur |

## Pourquoi un palier maintenant

La première livraison par la chaîne (1.3.9, 26/11/2026) s'est arrêtée au téléchargement des
images : GHCR a refusé l'agent. Sous systemd, Docker lisait la connexion `ghcr.io` de `root`,
périmée ; GHCR refuse un jeton invalide même pour une image publique. Rien n'avait redémarré,
mais l'agent avait déjà changé le code et sa reprise retéléchargeait les images, refusée elle
aussi. C'est le dixième correctif du cycle : la règle de versionnement en fait le palier.

Le même essai a montré, par le nouveau contrôle de sécurité, que l'interface reposait sur une
image nginx 1.27 qui n'était plus suivie : 3 failles critiques et 67 élevées, toutes corrigées
dans les paquets à jour.

## Ce qui change

Pour les utilisateurs : rien de visible. Pas de migration de base, pas de changement de l'API.

Pour l'exploitation :

- l'agent télécharge les images **avant** de toucher au serveur, avec des réglages Docker à lui,
  vides (`livraisons/docker`) : les images d'AMM GH sont publiques, aucune connexion n'est
  nécessaire, et celle de `root` (peut-être utile à JUSTI GH) n'est pas modifiée ;
- le retour à la version d'avant ne retélécharge rien : ses images sont déjà sur le serveur ;
- une faille critique corrigeable dans une image bloque la livraison d'une nouvelle version
  (jamais un retour volontaire à une version déjà publiée) ;
- interface sur `nginx:1.30-alpine` (branche stable) ; image backend mise à jour des correctifs
  Debian à chaque construction.

## Validation (26/11/2026)

| Contrôle | Résultat |
| --- | --- |
| Tests backend | 852 réussis (850 en 1.3.9), dont 19 tests de l'agent sur un vrai dépôt git |
| Migrations | aucune (`makemigrations --check`) |
| `pip-audit` sur `requirements.txt` | aucune vulnérabilité connue |
| `nginx -t` avec `docker/nginx.conf` sur nginx 1.30.8 | configuration valide |
| Trivy sur `nginx:1.30-alpine` (failles corrigeables) | 0 critique, 0 élevée (image 1.3.9 : 3 critiques, 67 élevées) |
| `apt-get upgrade` sur `python:3.12-slim` | `libzstd1` passe en `1.5.7+dfsg-1+deb13u1` (faille élevée corrigée) |
| Workflow : syntaxe bash et shellcheck de chaque étape | sans remarque |

Reste signalé, sans correctif à appliquer de notre côté : `setuptools 70.3.0` vu par Trivy est la
copie de `pkg_resources` embarquée par pip lui-même, pas un paquet installé ; les failles
élevées de Debian sans version corrigée (util-linux, tesseract) attendent Debian.

## Déploiement

La 1.4.0 passe par la chaîne elle-même : c'est son essai réel.

Au moment de l'approbation, c'est encore l'agent de la 1.3.9 qui tourne sur le serveur, et il
buterait sur GHCR. Il a donc été remis en état le 26/11/2026, sans changer de version, en lui
donnant par systemd les réglages Docker vides que la 1.4.0 pose elle-même :

```bash
sudo mkdir -p /etc/systemd/system/amm-gh-livraison.service.d /var/lib/amm-gh-livraison/docker
printf '[Service]\nEnvironment=DOCKER_CONFIG=/var/lib/amm-gh-livraison/docker\n' \
  | sudo tee /etc/systemd/system/amm-gh-livraison.service.d/docker.conf
sudo systemctl daemon-reload
```

puis éprouvé en relançant l'étape 3 de la Livraison 1.3.9 (réinstallation de la même version :
sauvegarde, images, contrôle de santé, rien ne redémarre). Ce réglage reste sans effet une fois la
1.4.0 en place, dont l'agent choisit lui-même ses réglages Docker.

1. Fusion de la pull request, puis étiquette `v1.4.0` depuis `main` à jour.
2. Livraison : vérification, contrôle de sécurité, images `1.4.0`, version publiée.
3. Approbation dans Actions > Livraison, hors des heures de travail ou quand personne n'utilise
   l'application.
4. L'agent : sauvegarde vérifiée, images, installation, contrôle de santé (`1.4.0`).

## Retour arrière

- **Automatique** : si l'API ne répond pas « ok » en 1.4.0 dans les 3 minutes, l'agent remet la
  1.3.9 (code et images déjà présents, rien n'est retéléchargé).
- **Volontaire** : Actions > Livraison > Run workflow, étiquette `v1.3.9`.
- **Base** : aucune migration dans ce palier ; la sauvegarde vérifiée prise par l'agent juste
  avant l'installation reste disponible (`scripts/serveur/restaurer_base.sh`).
