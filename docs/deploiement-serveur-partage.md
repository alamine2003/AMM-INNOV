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

## 2. Ouverture publique (à faire quand l'essai est concluant)

1. **Caddy de JUSTI GH.** Les fichiers de `/home/deploy/justi-innov` sont remplacés à chaque
   livraison : la modification se fait dans le dépôt de JUSTI GH, pas sur le serveur. Il faut
   un bloc de site pour `amm.102-203-86-8.sslip.io` qui transmet au nginx d'AMM GH, avec
   `request_body { max_size 260MB }` (dossiers pays) et un délai de lecture long.
   Ne pas brancher les deux applications sur un même réseau Docker : leurs services portent
   les mêmes noms (`frontend`, `backend`) et Caddy enverrait des visites de l'une à l'autre.
   Passer par un port de la machine (`AMM_BIND` sur l'adresse de la passerelle Docker,
   `host.docker.internal` côté Caddy).
2. **`.env` d'AMM GH** : `FRONTEND_URL=https://amm.102-203-86-8.sslip.io`,
   `AUTH_REFRESH_COOKIE_SECURE=1`, retirer les origines `http://localhost:8081` ; renseigner le
   stockage S3 (`DOCUMENT_STORAGE=s3`, `S3_*` : les scans restent sur Cloudflare R2, rien à
   déplacer) et Nextcloud (`NEXTCLOUD_USER`, `NEXTCLOUD_APP_PASSWORD`).
3. **Bascule** : arrêter les écritures sur Render, lancer une dernière sauvegarde (workflow
   « Base Render », action `backup`), `restaurer_base.sh … --remplacer`, `compose.sh up -d`,
   contrôler, puis faire pointer l'interface vers la nouvelle adresse.
4. **Retour arrière** : Render reste en place tant que la bascule n'est pas validée.

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
