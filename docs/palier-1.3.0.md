# Palier 1.3.0 : validation, déploiement, retour arrière

La 1.3.0 termine le deuxième écart du rapport d'architecture (l'hébergement) : AMM GH est prête
à quitter Render pour le Serveur 01 Stellarix, à côté de JUSTI GH. L'interface reste sur
Cloudflare Pages, les utilisateurs gardent leur adresse. Le contenu est dans `CHANGELOG.md`. Ce
document répond aux exigences d'un palier (`docs/versionnement.md`).

Le cycle 1.2 a préparé ce palier : sauvegardes de Render chiffrées et relues chaque nuit
(1.2.7), installation sur un serveur partagé (1.2.8), ouverture publique à travers le Caddy
déjà en place (1.2.9).

## Ce qui change pour les utilisateurs

Rien tant que la bascule n'est pas faite : sur Render, la 1.3.0 se comporte comme la 1.2.9 (la
surveillance des sauvegardes y est inactive). Après la bascule : la même adresse, la même
interface, une API qui ne s'endort plus et ne subit plus les limites de l'offre gratuite
(512 Mo de mémoire, Redis de 25 Mo, base à renouveler tous les 25 jours).

Le CEO peut recevoir un nouvel avertissement dans l'application : « Sauvegarde de la base : à
vérifier ».

Pas de migration de base de données. Aucun changement de l'API.

## Pourquoi la sauvegarde avant tout le reste

Sur Render, la base était sauvegardée par GitHub Actions. Sur le serveur, elle ne l'est plus :
la sauvegarde locale d'origine (`scripts/backup.sh`) écrivait en clair, sur la même machine,
sans jamais être relue. Une machine perdue aurait emporté la base et ses sauvegardes. La
bascule n'a donc de sens qu'après ceci :

| Exigence | Réponse de la 1.3.0 |
| --- | --- |
| Chiffrée | `pg_dump` chiffré au vol, aucune copie en clair sur le disque, refus sans phrase secrète |
| Relue | chaque sauvegarde est restaurée dans une base d'essai avant de compter |
| Hors de la machine | copie horaire dans le stockage des scans (Cloudflare R2), taille contrôlée |
| Surveillée | avertissement au CEO et contrôle d'intégrité si elle échoue, s'arrête ou n'est plus copiée |
| Restaurable par un autre | même format et même phrase secrète que Render : `verify_backup.sh`, `restaurer_base.sh` |

L'écart du 11 au 13 novembre (deux nuits sans sauvegarde, vu par hasard) ne peut plus passer
inaperçu : c'est l'application elle-même qui le dit.

## Validation (15/11/2026)

| Contrôle | Résultat |
| --- | --- |
| Tests backend (Postgres, Redis, Python 3.12, versions figées) | 744 réussis (733 en 1.2.9), couverture 91 % |
| Tests frontend (Vitest) | 176 réussis (interface inchangée) |
| Règles d'import des couches (`test_architecture.py`) | aucune exception |
| Migrations | aucune (`makemigrations --check`) |
| Schéma OpenAPI | inchangé |
| `pip-audit` sur `requirements.txt` | aucune vulnérabilité |
| `npm audit --omit=dev` (code livré) | aucune vulnérabilité |
| `check_integrity` | 15 contrôles : les 13 de la 1.2.9, plus `backup_verified` et `backup_offsite` |

Essais de bout en bout, dans des conteneurs (images `postgres:18`, backend et interface de la
1.2.8 avec le code de la 1.3.0) :

| Essai | Résultat |
| --- | --- |
| Sauvegarde sans phrase secrète | refusée, rien d'écrit, `etat.json` le dit |
| Sauvegarde d'une base vide | mise de côté (`.echec`), base d'essai retirée, `etat.json` le dit |
| Sauvegarde d'une base de démonstration | 66 tables, 100 migrations, relue et restaurée |
| Relecture par `scripts/verify_backup.sh` | refus avec une mauvaise phrase, réussite avec la bonne |
| Rétention sur le serveur | 5 anciennes retirées sur 10, les 7 dernières gardées |
| Phrase secrète avec espace et `$` | acceptée, intacte |
| Phrase secrète vue par l'application | non : présente dans le service `backup`, absente du backend et du worker |
| Dossier des sauvegardes vu du worker | lisible, en lecture seule, sous un compte sans privilège |
| Copie hors machine (vrai client S3, serveur S3 d'essai) | copiée une fois, pas renvoyée, ancienne retirée, scans intacts |
| Sans stockage S3 | avertissement « ne quittent pas le serveur », CEO prévenu une fois |
| `brancher_interface.sh https://amm-gh.pages.dev` | préflight CORS accepté, connexion réussie, cookie `SameSite=None; Secure`, renouvellement de session réussi |
| Origine inconnue | aucun en-tête d'autorisation |
| `brancher_interface.sh … --retirer` | configuration d'avant retrouvée |

La CI de la PR a d'abord échoué sur un test sans rapport avec ce palier (assemblage d'un
classeur) : ses machines sont passées d'Ubuntu 24.04 à 26.04 entre le 14 et le 15 novembre, et
ce système confine `qpdf` (AppArmor) aux fichiers `.pdf`, `.qdf` et `.json`. Corrigé dans ce
palier (voir `CHANGELOG.md`), avec un test qui tient sans ce confinement : tout fichier remis
à `qpdf` doit se terminer par `.pdf`. La production n'était pas touchée.

Non essayé ici, à contrôler pendant la bascule : la copie vers le vrai Cloudflare R2, le temps
réel depuis l'interface Cloudflare Pages, la synchronisation GHPL depuis le serveur.

## Sécurité

- La phrase secrète n'est ni dans le dépôt, ni dans `.env`, ni dans l'environnement de
  l'application : `.env.sauvegarde`, lisible par root, lu par le seul service `backup`. Une
  faille de l'application ne la livre pas.
- Aucun secret sur une ligne de commande : `configurer.sh` refuse toute clé au nom de secret
  donnée avec sa valeur. Rien ne reste dans l'historique du terminal.
- La copie hors machine ne contient que des fichiers chiffrés. La rotation ne retire que des
  fichiers nommés comme des sauvegardes, sous leur préfixe : un scan ne peut pas être touché.
- L'API n'accepte qu'une origine de plus, nommée (`https://amm-gh.pages.dev`), jamais `*`. Le
  cookie de session reste `HttpOnly`, `Secure`, limité au chemin `/api/v1/auth`.
- Le serveur n'ouvre aucun port de plus. La base n'est joignable que des conteneurs d'AMM GH.

Risques acceptés, à connaître :

- Les droits S3 de l'application permettent aussi d'effacer les sauvegardes distantes : un
  attaquant maître du serveur pourrait le faire. Les copies resteraient chiffrées. Réponse
  possible plus tard : un second jeu de droits S3, en écriture seule.
- Les scans ne sont pas sauvegardés ailleurs que sur Cloudflare R2, comme aujourd'hui.
- L'interface et l'API sont sur deux sites différents : Safari peut refuser le cookie de
  session entre les deux, comme aujourd'hui avec Render. Un nom de domaine commun le réglera.
- Une seule personne détient la phrase secrète. Il en faut une seconde.

## Déploiement

1. Fusionner la PR `version-1.3.0`. La CI de `main` doit être verte.
2. Render redéploie l'API tout seul : `/api/v1/health` répond `"version":"1.3.0"`. Rien d'autre
   ne change sur Render.
3. Poser le tag `v1.3.0` sur le merge.
4. Serveur : mise à jour (`docs/deploiement-serveur-partage.md`, section 5), puis sections 3
   (sauvegardes) et 4 (bascule), dans l'ordre : phrase secrète et première sauvegarde ; scans ;
   interface autorisée ; bascule à une heure creuse.

## Retour arrière

- **Avant la bascule** : rien à défaire pour les utilisateurs, Render est la production. Sur
  le serveur, `git checkout v1.2.9` puis `compose.sh up -d` revient à l'état d'avant ; les
  fichiers de sauvegarde restent lisibles.
- **Après la bascule** : Cloudflare Pages, *Deployments*, « Rollback to this deployment » sur
  le déploiement d'avant (il pointe vers Render), puis reprendre le service Render. Les saisies
  faites sur le serveur entre-temps ne sont pas sur Render : ce retour n'est sûr que dans les
  premières heures. Au-delà, on répare en avant, avec la sauvegarde de la nuit.
- **Code** : `git revert` du merge de la 1.3.0 sur une branche `version-1.3.1`, puis PR. Sans
  migration ni changement de données, c'est sans risque.

## Reste à faire après le palier

- Arrêter Render, le Worker Cloudflare qui le réveille et le workflow « Base Render », après
  quelques jours sans incident.
- Un nom de domaine propre (l'adresse du serveur n'apparaît plus nulle part).
- Note dans le dépôt de JUSTI GH sur l'application voisine (`caddy/voisins/`).
- Seconde personne détentrice de la phrase secrète.
