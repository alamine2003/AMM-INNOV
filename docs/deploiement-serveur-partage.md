# AMM GH sur un serveur partagé (Serveur 01 Stellarix, à côté de JUSTI GH)

Depuis la 1.2.8, AMM GH peut tourner sur une machine dont les ports web (80 et 443) sont déjà
tenus par une autre application. C'est le cas du Serveur 01 Stellarix : le Caddy de JUSTI GH
y reçoit toutes les visites de l'adresse publique.

```
/home/deploy/
├── justi-innov/    JUSTI GH, inchangée
└── amm-gh/         AMM GH : ce guide
```

Chaque application garde son dossier, ses conteneurs (`amm-gh-…`), sa base et ses volumes.
AMM GH n'ouvre aucun port public : son nginx écoute sur `127.0.0.1:8081`, visible de la machine
seulement. Sa mémoire est plafonnée par service (environ 4,5 Go au plus, 0,7 Go au repos).

## 1. Essai privé (ne touche à aucun fichier de JUSTI GH)

Sur le serveur, avec un compte qui a `sudo` :

```bash
sudo git clone https://github.com/alamine2003/AMM-INNOV.git /home/deploy/amm-gh
cd /home/deploy/amm-gh
sudo git checkout v1.2.8                      # ou un tag plus récent
sudo scripts/serveur/preparer_env.sh amm.102-203-86-8.sslip.io --essai
```

`preparer_env.sh` crée `.env` avec des secrets tirés au hasard sur place (personne ne les
saisit). Il ne l'écrase jamais.

Copie de la base : envoyer une sauvegarde chiffrée sur le serveur (depuis le poste,
`scp amm-render-….dump.gpg compte@serveur:/tmp/`), puis

```bash
sudo scripts/serveur/restaurer_base.sh /tmp/amm-render-AAAAMMJJ-HHMMSS.dump.gpg
sudo scripts/serveur/compose.sh up -d
sudo scripts/serveur/compose.sh ps            # tout doit être « healthy »
```

La phrase secrète des sauvegardes est demandée au clavier. Une base déjà remplie est refusée,
sauf avec `--remplacer` (elle est alors effacée, puis recréée depuis la sauvegarde).

Ouvrir l'application depuis son poste, par un tunnel SSH :

```bash
ssh -L 8081:127.0.0.1:8081 compte@serveur     # laisser cette fenêtre ouverte
```

puis `http://localhost:8081` dans le navigateur. On se connecte avec son compte habituel : la
copie de la base contient les comptes.

Pendant l'essai :

- les scans ne s'ouvrent pas (le stockage S3 n'est pas renseigné, `DOCUMENT_STORAGE=local`) ;
- la synchronisation GHPL est inactive (pas d'identifiants Nextcloud) ;
- aucun e-mail ne part ; la production (Render) n'est pas touchée.

## 2. Ouverture publique (quand l'essai est concluant)

```bash
cd /home/deploy/amm-gh
sudo scripts/serveur/ouvrir_public.sh
```

Le script ouvre `https://<DOMAIN du .env>` à travers le Caddy déjà en place (le « portier »),
en cinq étapes, et s'arrête à la première anomalie :

1. le nginx d'AMM GH écoute sur la passerelle Docker (`172.17.0.1:8081`) au lieu de la boucle
   locale : joignable de la machine et de ses conteneurs, jamais de l'extérieur ;
2. le portier doit le joindre : c'est contrôlé **avant** de toucher à sa configuration ;
3. chez le portier (`/home/deploy/justi-innov`) : le fichier `caddy/voisins/amm-gh.caddy` et,
   une seule fois, la ligne `import caddy/voisins/*.caddy` à la fin de son Caddyfile (copie de
   sauvegarde `Caddyfile.avant-amm-gh`) ;
4. Caddy valide la configuration ; refusée, le fichier est retiré et rien n'est rechargé ;
   acceptée, il la recharge sans couper les visites en cours ;
5. AMM GH passe en HTTPS : adresse publique, cookie de session réservé à HTTPS.

Les deux applications ne partagent aucun réseau Docker : leurs services portent les mêmes
noms (`frontend`, `backend`) et Caddy enverrait des visites de l'une à l'autre. Le portier
joint AMM GH par un port de la machine.

`sudo scripts/serveur/ouvrir_public.sh --fermer` retire le site et revient à l'essai privé.
Le script se relance sans risque : à refaire après toute mise à jour des fichiers du portier
qui remplacerait son Caddyfile (un acte d'exploitation côté JUSTI GH, jamais une livraison).

Une fois ouverte, l'accès par tunnel passe par la passerelle :
`ssh -L 8081:172.17.0.1:8081 compte@serveur`.

La mise en service réelle (sauvegardes, scans, bascule depuis Render) est décrite aux
sections 3 et 4.

## 3. Sauvegardes (palier 1.3.0)

Chaque nuit à `BACKUP_HOUR` (2 h), le service `backup` lance `scripts/serveur/sauvegarder.sh` :

1. `pg_dump` de la base, **chiffré au vol** (gpg AES256). Aucune copie en clair n'est écrite
   sur le disque. Sans phrase secrète, la sauvegarde est refusée, et c'est dit.
2. **Essai de restauration** : le fichier chiffré est relu et restauré dans une base d'essai
   (`amm_essai_restauration`), à côté de la vraie, puis contrôlé (tables, migrations, fiches
   AMM, produits, pays, comptes). La base d'essai est supprimée. Une sauvegarde qui ne se relit
   pas est mise de côté (`.echec`) et ne compte pas.
3. Le fichier vérifié, `backups/amm-vm-AAAAMMJJ-HHMMSS.dump.gpg`, a le format des sauvegardes de
   Render : `scripts/verify_backup.sh` et `restaurer_base.sh` le relisent tels quels.
4. `backups/etat.json` dit ce qui s'est passé.

Le worker lit ce dossier en lecture seule (tâche `ship_backups`, chaque heure) :

- il **copie hors de la machine** chaque sauvegarde vérifiée, dans le stockage des scans (S3),
  sous `sauvegardes/base/`. Actif dès que `DOCUMENT_STORAGE=s3` ;
- il **avertit dans l'application** chaque CEO (une fois par jour au plus) si la sauvegarde a
  échoué, n'a pas tourné depuis 30 heures, ou n'est plus copiée hors de la machine. Les mêmes
  constats figurent au contrôle d'intégrité de 5 h (`backup_verified`, `backup_offsite`).

Rétention : 30 jours sur le serveur (`BACKUP_RETENTION_DAYS`) comme hors machine
(`BACKUP_REMOTE_RETENTION_DAYS`), et jamais les 7 dernières, même plus anciennes.

**La phrase secrète** est celle des sauvegardes de Render (`BACKUP_PASSPHRASE`). Elle est
saisie une fois, sans s'afficher, et rangée dans `.env.sauvegarde` : seul le service `backup`
la lit, l'application ne la connaît pas.

```bash
cd /home/deploy/amm-gh
sudo scripts/serveur/configurer.sh BACKUP_PASSPHRASE          # demandée deux fois, masquée
sudo scripts/serveur/compose.sh up -d
sudo scripts/serveur/compose.sh exec backup /scripts/serveur/sauvegarder.sh   # première sauvegarde
```

La dernière ligne doit finir par `OK : amm-vm-… relue et restaurée`.

Relire une sauvegarde ailleurs (un poste avec Docker) : `scripts/verify_backup.sh fichier.dump.gpg`.
La restaurer sur le serveur : `sudo scripts/serveur/restaurer_base.sh fichier.dump.gpg --remplacer`.

Limites connues : les scans ne sont pas dans ces sauvegardes (ils vivent sur le stockage S3,
qui est leur lieu de conservation) ; la copie hors machine utilise les mêmes droits S3 que
l'application ; perdre la phrase secrète rend toutes les sauvegardes illisibles (en garder
une copie hors du serveur, chez deux personnes).

`scripts/serveur/configurer.sh` règle toute autre valeur de `.env` sans l'éditer à la main :
un secret (nom contenant KEY, SECRET, PASSWORD, PASSPHRASE ou TOKEN) est toujours demandé au
clavier, jamais accepté sur la ligne de commande ; une valeur ordinaire s'écrit `CLE=valeur`.

## 4. Bascule depuis Render (palier 1.3.0)

L'interface reste sur Cloudflare Pages (`https://amm-gh.pages.dev`) : les utilisateurs gardent
leur adresse. Seule l'API change de machine. Render reste intact jusqu'à la fin : c'est le
retour arrière.

**a. Scans** (avant la bascule ; les scans restent sur Cloudflare R2, rien à déplacer). Les
valeurs sont celles du service Render (tableau de bord, *Environment*) :

```bash
sudo scripts/serveur/configurer.sh DOCUMENT_STORAGE=s3 S3_REGION=auto S3_ADDRESSING_STYLE=path
sudo scripts/serveur/configurer.sh S3_ENDPOINT_URL=https://<compte>.r2.cloudflarestorage.com S3_BUCKET=<bucket>
sudo scripts/serveur/configurer.sh S3_ACCESS_KEY
sudo scripts/serveur/configurer.sh S3_SECRET_KEY
sudo scripts/serveur/compose.sh up -d
```

Contrôle : un scan s'ouvre dans l'application du serveur, et dans l'heure la sauvegarde
apparaît hors machine (`sudo scripts/serveur/compose.sh exec worker python manage.py
check_integrity` : `backup_offsite` est `OK`). Tant que le serveur porte une copie d'essai de
la base, ne pas y travailler (import, suppression, export de classeur) : les deux instances
partagent les mêmes scans.

**b. Interface Cloudflare Pages autorisée sur l'API du serveur** :

```bash
sudo scripts/serveur/brancher_interface.sh https://amm-gh.pages.dev
```

Le script ajoute l'adresse aux origines acceptées (appels, formulaires, temps réel), fait
mener les liens des notifications à cette interface, passe le cookie de session en
`SameSite=None`, redémarre, puis contrôle que l'API répond bien à cette origine. `--retirer`
fait l'inverse.

**c. Bascule**, à une heure creuse, dans cet ordre :

1. Render : suspendre le service `amm-innov-api` (plus aucune écriture possible).
2. GitHub : workflow « Base Render », action `backup` ; télécharger l'artefact, le copier sur
   le serveur (`scp`).
3. Serveur : `sudo scripts/serveur/restaurer_base.sh amm-render-….dump.gpg --remplacer`.
4. Serveur : synchronisation GHPL, une seule instance à la fois :
   `sudo scripts/serveur/configurer.sh NEXTCLOUD_USER=<compte>`, puis
   `sudo scripts/serveur/configurer.sh NEXTCLOUD_APP_PASSWORD`, puis
   `sudo scripts/serveur/compose.sh up -d`.
5. Serveur : `sudo scripts/serveur/compose.sh exec backup /scripts/serveur/sauvegarder.sh`
   (première sauvegarde de la vraie base).
6. Cloudflare Pages, projet `amm-gh`, *Settings → Environment variables* :
   `VITE_API_BASE=https://<DOMAIN>` et `VITE_WS_URL=wss://<DOMAIN>/ws/`, puis redéployer.
7. Contrôles : connexion, nombre d'AMM, un scan, pastille « Live », une saisie puis sa
   relecture.

**Retour arrière** (tant que rien d'important n'a été saisi sur le serveur) : Cloudflare
Pages, *Deployments*, « Rollback to this deployment » sur le déploiement d'avant (il pointe
vers Render), puis reprendre le service Render. Ce qui a été saisi sur le serveur entre-temps
n'est pas sur Render : au-delà de quelques heures, on répare en avant plutôt que de revenir.

**Après quelques jours sans incident** : arrêter le service Render, le Worker Cloudflare qui
le réveille, et le workflow « Base Render ».

## 5. Mettre à jour

```bash
cd /home/deploy/amm-gh
sudo git fetch --tags && sudo git checkout vX.Y.Z
sudo scripts/serveur/compose.sh pull
sudo scripts/serveur/compose.sh up -d
```

`TAG` dans `.env` choisit l'image (`latest`, ou le début d'un commit pour figer une version).

### Surveiller la mémoire

```bash
sudo docker stats --no-stream | grep amm-gh
sudo docker exec amm-gh-backend-1 cat /sys/fs/cgroup/memory.events
```

`max` compte les fois où un service a buté sur sa limite (il ralentit), `oom_kill` celles où il
a été coupé. Les deux doivent rester à zéro. Les limites se règlent sans toucher aux fichiers :
`sudo scripts/serveur/configurer.sh AMM_MEM_BACKEND=2g` puis `compose.sh up -d`
(`AMM_MEM_WORKER`, `AMM_MEM_POSTGRES` de même). Le 18/11/2026, l'API à 1 Go avait buté 2 014
fois en 19 heures : limite portée à 2 Go, cause corrigée en 1.3.4.

## 6. Tout enlever

```bash
cd /home/deploy/amm-gh && sudo scripts/serveur/compose.sh down     # garde les données
sudo scripts/serveur/compose.sh down -v                            # efface aussi base et scans locaux
```

JUSTI GH n'est concernée par aucune de ces commandes.
