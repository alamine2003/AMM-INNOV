# Audit d'infrastructure — 11/11/2026 (versions 1.2.4 et 1.2.5)

Rapport complet : document « Audit d'infrastructure — AMM GH » (Claude Docs). Ce fichier garde
les constats, ce que les versions 1.2.4 et 1.2.5 corrigent, et les gestes faits à la main.

## Infrastructure en place

| Élément | Hébergement | Limites |
|---|---|---|
| Interface React | Cloudflare Pages (`amm-gh.pages.dev`) | aucune gênante |
| API + WebSocket + Celery + beat | Render gratuit, **un seul conteneur** (`AMM_ROLE=all`) | 512 Mo, 0,1 CPU, mise en veille après 15 min sans requête, 750 h/mois |
| PostgreSQL | Render gratuit | 1 Go, **supprimée après 30 jours** (renouvelée par `render-db.yml`) |
| Redis (broker, cache, temps réel) | Render Key Value gratuit | 25 Mo, `noeviction` |
| Scans | Cloudflare R2 | — |
| Sauvegardes | artefacts GitHub Actions | dépôt **public** |

## Constats

| # | Gravité | Constat | Correction |
|---|---|---|---|
| 1 | Critique | 56 copies complètes de la base publiées en clair en artefacts d'un dépôt public. | 1.2.4 : chiffrement ; 55 copies supprimées le 11/11, `amm-db-58` gardée en attendant la première sauvegarde chiffrée |
| 2 | Haute | Réveil GitHub parti 3 à 7 fois par jour au lieu de 144 : veille, démarrages à froid (~1 min), Celery arrêté entre deux visites. | Worker `amm-gh-keepalive` créé le 11/11 (Cron `*/5 * * * *`) |
| 3 | Haute | Sonde Render sur `/health` (base comprise) : une base lente fait redémarrer l'API. | 1.2.4 ; vérifié dans Render le 11/11 |
| 4 | Haute | Celery lancé en arrière-plan sans surveillance : s'il meurt, rien ne le relance. | Relance automatique |
| 5 | Haute | Après chaque déploiement, les onglets ouverts plantent (« Unexpected Application Error »). | Rechargement automatique, page d'erreur |
| 6 | Moyenne | `/metrics` public (nombre d'AMM par statut, e-mails…). | Fermé sans jeton |
| 7 | Moyenne | Web, worker et beat dans 512 Mo : l'analyse d'un dossier pays a déjà tué l'instance (24/09). | Limite de l'offre ; journal des erreurs (1.2.5) pour voir les pannes |
| 8 | Moyenne | Base renouvelée tous les 25 jours : redéploiement, et l'horaire GitHub dérive (exécutée vers 9-10 h au lieu de 2 h 30). | 1.2.5 : renouvellement de nuit seulement (0 h - 7 h), forcé à 28 jours |
| 9 | Moyenne | Redis 25 Mo partagé (broker, cache, temps réel) sans éviction : plein, les écritures échouent. | 1.2.5 : contrôle d'intégrité et avertissement au CEO à 80 % |
| 10 | À vérifier | Compteur de 1 099 e-mails envoyés alors qu'aucun e-mail d'alerte n'est voulu. | 1.2.5 : e-mails d'alerte coupés par défaut (`ALERT_EMAILS_ENABLED`) |
| 11 | À vérifier | Sans `SENTRY_DSN` / `VITE_SENTRY_DSN`, les plantages ne sont vus par personne. | 1.2.5 : journal des erreurs dans AMM GH (Administration › Erreurs) |

## Gestes manuels

1. ~~Supprimer les artefacts `amm-db-*`~~ : fait le 11/11 (55 sur 56). `amm-db-58` reste
   jusqu'à la première sauvegarde chiffrée, puis se supprime (GitHub › Actions › « Base
   Render » › exécution › Artifacts › corbeille).
2. **Créer le secret `BACKUP_PASSPHRASE`** (GitHub › Settings › Secrets and variables ›
   Actions) : une longue phrase secrète, gardée aussi hors de GitHub (sans elle, les
   sauvegardes sont illisibles). Déchiffrer :
   `gpg --decrypt amm-render-AAAAMMJJ-HHMMSS.dump.gpg > amm.dump`.
3. ~~Installer le réveil Cloudflare~~ : fait le 11/11 (Worker `amm-gh-keepalive`, Cron
   `*/5 * * * *`, code de `scripts/cloudflare/keepalive-worker.js`).
4. ~~Sonde de santé Render~~ : déjà `/api/v1/health/live` (vérifié le 11/11).
5. **Restauration d'essai** (1.2.7) : chaque sauvegarde chiffrée est restaurée dans une base
   jetable par le workflow (`scripts/verify_backup.sh`). Sur un poste, le même script prouve
   que la copie de la phrase secrète gardée hors de GitHub fonctionne.
6. Ne pas renseigner `ALERT_EMAILS_ENABLED` tant que la direction ne veut pas d'e-mails
   d'alerte. Sentry n'est plus nécessaire : le journal des erreurs est dans l'application.

## Suite recommandée

Le reste tient à l'offre gratuite : un conteneur de 512 Mo qui fait tout, une base à
renouveler, un Redis de 25 Mo. La sortie durable est de faire tourner l'API sur le serveur
Hetzner (déjà utilisé par JUSTI GH) avec `docker-compose.prod.yml` : web, worker et beat
séparés, PostgreSQL et Redis sans limite de durée, sauvegardes sur le serveur. C'est aussi la
première étape de la migration Kubernetes prévue pour JUSTI GH et AMM GH.

## Retour arrière

Aucune migration de base. Revenir au tag `v1.2.3` ; remettre `/api/v1/health` comme sonde
si besoin. Le Worker Cloudflare se supprime depuis le tableau de bord.
