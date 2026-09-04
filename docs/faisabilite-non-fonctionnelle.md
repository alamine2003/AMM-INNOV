# Étude de faisabilité non fonctionnelle — AMM INNOV

| Champ | Valeur |
|---|---|
| Version | 1.0 |
| Date | 04/09/2026 |
| Documents liés | [PRD](../prd.md) · [Architecture](../architecture.md) · [Faisabilité fonctionnelle](faisabilite-fonctionnelle.md) |

## 1. Objet

Évaluer la capacité de la stack retenue (React + TypeScript, Django + DRF, PostgreSQL, Redis, Celery, Django Channels, Grafana, Docker) à satisfaire les exigences non fonctionnelles du PRD, chiffrer les ressources, et identifier les risques techniques.

## 2. Volumétrie de référence

| Grandeur | Valeur actuelle | Projection à 5 ans |
|---|---|---|
| AMM | 1 548 | 3 000 |
| Renouvellements | ~1 000 (un par AMM au plus dans le classeur) | 5 000 |
| Documents PDF | 0 (à collecter), cible 2 à 3 par AMM | 10 000 fichiers, ~30 Go |
| Alertes générées par an | ~500 | 1 000 |
| Utilisateurs | ~20 (15 pays + siège + direction) | 40 |
| Utilisateurs simultanés | 5 à 10 | 20 |
| Requêtes API par jour | < 20 000 | 50 000 |

Conclusion : volumétrie faible. Un serveur unique de 4 vCPU et 8 Go de RAM est suffisant ; la conception doit privilégier la fiabilité et la traçabilité plutôt que la montée en charge.

## 3. Faisabilité par exigence

| # | Exigence (PRD §8) | Cible | Faisabilité | Moyens | Preuve attendue |
|---|---|---|---|---|---|
| N1 | Performance liste AMM | < 1 s pour 2 000 lignes filtrées | Acquise | Index sur `(country, status)`, `effective_end_date`, `urgency` ; pagination 50 ; champs calculés dénormalisés | Test de charge k6 : p95 < 300 ms sur `/amms` avec 3 000 AMM |
| N2 | Performance dashboard | < 2 s | Acquise | Agrégats ORM sur 3 000 lignes ; vues matérialisées pour Grafana | Mesure p95 sur `/analytics/africa` |
| N3 | Temps réel | Propagation < 2 s | Acquise | Django Channels + Redis ; message d'invalidation léger ; TanStack Query refetch | Test Playwright : deux navigateurs, modification visible < 2 s |
| N4 | Disponibilité | 99,5 % heures ouvrées | Acquise sous condition | Docker avec `restart: unless-stopped`, healthchecks, sauvegardes ; pas de haute disponibilité multi-nœuds | Choix d'un hébergeur avec SLA ≥ 99,5 % ; supervision Grafana |
| N5 | Sécurité authentification | JWT court + refresh, Argon2, verrouillage | Acquise | simplejwt, django-axes, limitation de débit DRF | Tests d'intégration sur 401/403, revue OWASP ASVS niveau 2 |
| N6 | Cloisonnement par pays | Aucune fuite hors périmètre | Acquise | Filtrage systématique des querysets côté serveur, tests dédiés par rôle | Tests d'intégration : 404 hors périmètre, 403 en écriture |
| N7 | Confidentialité des documents | Accès contrôlé, jamais public | Acquise | URL signées 5 min, contrôle du périmètre avant remise du fichier, stockage hors webroot | Test : accès direct sans jeton refusé |
| N8 | Intégrité des documents | Fichier non altéré | Acquise | SHA-256 à l'upload, vérifié à la restauration ; versionnage sans écrasement | Script de vérification de sauvegarde |
| N9 | Auditabilité | Qui, quoi, quand | Acquise | django-simple-history sur toutes les entités métier | Endpoint `/history` testé |
| N10 | Sauvegarde et restauration | Quotidienne, rétention 30 j, RPO 24 h, RTO 4 h | Acquise | `pg_dump` + copie du stockage documentaire, scripts de restauration, test mensuel | Procédure documentée et rejouée |
| N11 | Fuseaux et dates | Stockage UTC, affichage local | Acquise | Django `USE_TZ`, calculs quotidiens en `Africa/Dakar` | Tests unitaires sur les bornes de dates |
| N12 | Langue | Français, i18n prêt | Acquise | i18next côté client, `gettext` côté serveur | — |
| N13 | Compatibilité navigateurs | 2 dernières versions Chrome/Edge/Firefox/Safari | Acquise | Vite cible ES2020, MUI | Smoke test Playwright multi-navigateurs |
| N14 | Accessibilité | Contraste AA, clavier | Acquise sous condition | Composants MUI accessibles ; Data Grid navigable au clavier | Audit axe-core sur les pages principales |
| N15 | Observabilité | Métriques, logs, alertes techniques | Acquise | django-prometheus, structlog, Grafana | Dashboard Technique opérationnel |
| N16 | Maintenabilité | Code typé, testé, CI | Acquise | TypeScript strict, mypy, ruff, pytest ≥ 80 % sur le cœur, GitHub Actions | Pipeline vert obligatoire pour fusionner |
| N17 | Portabilité | Déployable sur tout hôte Docker | Acquise | Compose dev et prod, images GHCR | Déploiement de recette réussi |
| N18 | Connectivité dégradée (pays) | Utilisable avec latence élevée | Acquise sous condition | Bundle < 1 Mo gzip, pagination, repli polling, emails de secours | Test avec limitation réseau 3G |

## 4. Choix techniques et alternatives

| Besoin | Choix | Alternatives étudiées | Motif du choix |
|---|---|---|---|
| Framework backend | Django + DRF | FastAPI, NestJS | ORM mature, admin intégré, écosystème complet (auth, historique, tâches, WebSocket) ; demandé par le client |
| Temps réel | Django Channels + Redis | SSE, polling seul, Socket.IO | Intégration native Django, groupes par pays |
| Tâches planifiées | Celery + django-celery-beat | cron, Django-Q, APScheduler | Retries, monitoring, planification en base |
| Base de données | PostgreSQL 16 | MySQL, SQLite | Vues matérialisées, JSONB, rôles fins pour Grafana ; demandé par le client |
| Stockage documentaire | Système de fichiers (dev) / S3-compatible MinIO (prod) via django-storages | BLOB en base | Sauvegarde et volumétrie découplées de la base |
| Frontend | React + TypeScript + Vite | Angular, Vue | Demandé par le client ; écosystème de grilles éditables |
| Grille éditable | MUI X Data Grid | AG Grid, Handsontable | Gratuit en édition communautaire, cohérent avec MUI |
| Restitution | Grafana | Metabase, tableaux internes uniquement | Demandé par le client ; provisioning en code |
| Reverse proxy TLS | Caddy | nginx + certbot, Traefik | Certificats automatiques, configuration minimale |

## 5. Dimensionnement

| Composant | Ressources dev | Ressources prod | Remarques |
|---|---|---|---|
| PostgreSQL | 1 vCPU, 1 Go | 2 vCPU, 2 Go, 20 Go disque | Base < 1 Go la première année |
| Redis | 256 Mo | 512 Mo | Channel layer + broker |
| Backend (Daphne) | 1 vCPU, 512 Mo | 2 workers, 1 Go | ASGI, WebSocket inclus |
| Celery worker + beat | 512 Mo | 1 vCPU, 1 Go | Charge concentrée la nuit et sur les imports |
| Frontend (nginx) | 64 Mo | 128 Mo | Statique |
| Grafana | 256 Mo | 512 Mo | |
| Stockage documents | 5 Go | 50 Go extensible | MinIO ou S3 managé |
| **Total** | 4 Go | **4 vCPU, 8 Go, 100 Go** | Un VPS standard |

Coût d'hébergement indicatif : 40 à 80 € par mois pour un VPS de cette taille, hors nom de domaine et emails transactionnels.

## 6. Sécurité : analyse des menaces principales

| Menace | Contrôle |
|---|---|
| Vol de jeton | Access 15 min en mémoire, refresh rotatif, révocation à la déconnexion |
| Accès hors périmètre pays | Filtrage serveur systématique, tests automatisés par rôle |
| Injection | ORM paramétré, validation DRF, CSP stricte |
| Upload malveillant | Type MIME réel vérifié, PDF assainis, taille limitée, stockage hors webroot |
| Force brute | Verrouillage après 10 échecs, limitation de débit |
| Perte de données | Sauvegardes chiffrées quotidiennes, test de restauration mensuel |
| Dépendances vulnérables | Dependabot hebdomadaire, images de base mises à jour |

## 7. Risques techniques

| Risque | Probabilité | Impact | Réponse |
|---|---|---|---|
| Latence réseau élevée dans certains pays | Élevée | Expérience dégradée | Bundle léger, pagination, repli polling, emails |
| Dérive entre formules Excel et calcul applicatif | Moyenne | Perte de confiance | Test de non-régression sur les totaux du classeur, comparaison statut par statut à l'import |
| Croissance du stockage documentaire | Faible | Coût | Stockage objet extensible, compression des PDF à l'upload |
| Indisponibilité du serveur unique | Faible | Interruption | Restauration en < 4 h sur un nouvel hôte grâce aux images et sauvegardes |
| Verrouillage fournisseur email | Faible | Alertes non envoyées | `EMAIL_URL` interchangeable, file d'attente avec retries |

## 8. Conclusion

Toutes les exigences non fonctionnelles sont atteignables avec la stack retenue sur une infrastructure modeste (un serveur de 4 vCPU et 8 Go). Les points de vigilance sont la connectivité des utilisateurs pays, la fidélité des calculs par rapport au classeur, et la discipline de sauvegarde. Aucun besoin ne justifie une architecture distribuée ou des composants supplémentaires.
