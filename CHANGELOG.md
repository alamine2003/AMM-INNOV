# Changelog

Toutes les évolutions notables du projet sont consignées ici.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnement [SemVer](https://semver.org/lang/fr/).

## [1.0.0] — 2026-09-05

Première version de production : remplacement du classeur `Dashboard AMM Afrique`.

### Fonctionnel
- Authentification JWT, trois rôles (`CEO_ADMIN`, `HQ_REGULATORY`, `COUNTRY_REGULATORY`), périmètre par pays.
- Référentiels pays, gammes, produits (alias Excel, fusion de doublons).
- AMM : création, édition en ligne, calcul du statut et de l'urgence, historique complet, export Excel/CSV.
- Workflow de renouvellement PLANIFIE → EN_PREPARATION → DEPOSE → EN_INSTRUCTION → OBTENU | REJETE | ABANDONNE.
- Moteur d'alertes paramétrable (J-365, J-180, J-90, J-30, J0, dossier incomplet, décision en retard), escalade siège puis CEO, résolution automatique.
- Notifications in-app temps réel (WebSocket, repli polling), emails, digest hebdomadaire.
- Tableaux de bord Afrique, pays et produit ; cinq dashboards Grafana provisionnés.
- Import idempotent du classeur Excel avec rapport d'anomalies.
- Gestion documentaire : scans PDF versionnés, chronologie inverse, visionneuse, archive ZIP, bibliothèque.

### Exploitation
- Docker Compose dev et prod (Caddy TLS, sauvegarde quotidienne), images GHCR, CI GitHub Actions, workflow Deploy.
- Commande `evaluate_alerts --quiet` et réglage `ALERTS_DISPATCH_MAX_AGE_DAYS` pour une mise en service sans déluge d'emails.
