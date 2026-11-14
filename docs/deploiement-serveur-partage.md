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

**Avant la mise en service réelle**, il reste à faire dans `.env` (puis
`scripts/serveur/compose.sh up -d`) :

- le stockage des scans : `DOCUMENT_STORAGE=s3` et les `S3_*` (les scans restent sur
  Cloudflare R2, rien à déplacer) ;
- la synchronisation GHPL : `NEXTCLOUD_USER`, `NEXTCLOUD_APP_PASSWORD` ;
- la bascule : arrêter les écritures sur Render, lancer une dernière sauvegarde (workflow
  « Base Render », action `backup`), `restaurer_base.sh … --remplacer`, contrôler, puis faire
  pointer les utilisateurs vers la nouvelle adresse. Render reste le retour arrière tant que
  la bascule n'est pas validée.

## 3. Mettre à jour

```bash
cd /home/deploy/amm-gh
sudo git fetch --tags && sudo git checkout vX.Y.Z
sudo scripts/serveur/compose.sh pull
sudo scripts/serveur/compose.sh up -d
```

`TAG` dans `.env` choisit l'image (`latest`, ou le début d'un commit pour figer une version).

## 4. Tout enlever

```bash
cd /home/deploy/amm-gh && sudo scripts/serveur/compose.sh down     # garde les données
sudo scripts/serveur/compose.sh down -v                            # efface aussi base et scans locaux
```

JUSTI GH n'est concernée par aucune de ces commandes.

## Sauvegardes sur le serveur

Le service `backup` écrit chaque nuit une copie locale dans `./backups` (30 jours). Elle ne
remplace pas une copie hors machine : à la mise en service, prévoir l'envoi chiffré vers un
autre lieu (le Serveur 02, ou le stockage S3), avec la même phrase secrète.
