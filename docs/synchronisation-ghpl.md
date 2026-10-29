# Synchronisation avec le classement AMM GHPL

Depuis la version 1.1.0, AMM GH suit tout seul le classement **AMM GHPL - CLASSEMENT GENERAL**
rangé sur Nextcloud, dans `ALAMINE NEXTCLOUD/AMM GHPL - CLASSEMENT GENERAL`. C'est le dossier que le client Nextcloud du Mac tient à jour. L'ancienne copie à la racine, `AMM GHPL - CLASSEMENT GENERAL`, n'est plus mise à jour depuis le 16/10. Ce classement est mis à jour par sa propre tâche planifiée. AMM GH relit
son registre (`0_REGISTRE AMM GHPL.xlsx`) chaque heure, à H+20. S'il a manqué un passage (Render
endormi), il le rattrape dans les cinq minutes qui suivent son réveil.

L'état de la synchronisation est visible dans **Imports Excel**, carte « Synchronisation avec AMM
GHPL ». Le bouton « Synchroniser maintenant » lance un passage à la demande.

## Ce qu'un passage fait

1. **Version du registre.** AMM GH lit la version du registre (une requête WebDAV
   `PROPFIND`). Si le registre n'a pas changé et qu'aucun scan n'attend, le passage s'arrête :
   « Déjà à jour ».
2. **Lecture du registre.** AMM GH télécharge le registre et en tire les pièces avec les règles
   du manifeste : période, type, date, n°, exemplaire principal, libellé du Dashboard. Il ne
   réimporte que les présentations dont le classement a changé depuis le dernier passage, par
   les mêmes imports que dans Imports Excel :
   - le registre GHPL, qui complète les fiches et ouvre les dépôts ;
   - puis les scans classés.

   Les lots qui en résultent apparaissent dans l'historique des imports, avec l'étiquette
   « Synchro AMM GHPL ».
3. **Les fiches ne sont jamais réécrites.** La synchronisation complète une fiche et crée l'AMM
   ou le renouvellement qui manque. Elle ne corrige jamais une date déjà sur la fiche : une
   correction faite dans AMM GH (classeurs, fiche, renouvellement) reste. Quand le classement dit
   autre chose, la pièce est marquée « à vérifier » dans le lot.
4. **Les pièces deviennent des documents de la fiche.**
   - Une pièce déjà envoyée (même nom sur la fiche, ou même fichier) est rattachée sans être
     téléchargée.
   - Une pièce reclassée (autre période, type, date, voire autre AMM) est suivie par son
     document. Il n'y a pas de doublon.
   - Une pièce nouvelle est téléchargée et rangée. AMM GH en traite 80 par passage au plus
     (`GHPL_SYNC_MAX_FILES`) ; la suite passe au passage suivant.
   - Une pièce au format Word, de plus de 25 Mo, ou illisible est laissée de côté et listée.
     Pour la faire entrer, enregistrez-la en PDF ou compressez-la dans le classement.
   - Une pièce retirée du classement est listée. Son document est conservé : AMM GH ne
     supprime jamais rien.
5. **Fiches en double.** Chaque fois qu'il relit le registre, AMM GH cherche, pays par pays, les
   fiches qu'aucun libellé du registre du pays ne désigne et qui sont la même présentation qu'une
   fiche du pays (même marque, forme, dosages et boîte), ouvertes sous le libellé d'un autre pays.
   Elles sont listées dans la carte, sous « Fiches en double » :
   - une **simple copie** (aucun document, aucun dossier de dépôt ni import de dossier, des dates,
     un n° d'origine et des renouvellements identiques) peut être fusionnée dans la fiche du pays
     (« Fusionner ») ; la fusion ne perd rien et reste dans l'historique ;
   - les autres sont « à vérifier », avec la différence trouvée : à régler à la main.

   Rien n'est fusionné sans qu'une personne le demande.
6. **Garde-fou.** Si le registre compte 10 % de pièces de moins qu'au passage précédent (par
   exemple parce qu'il est en cours d'écriture), rien n'est appliqué. Le passage est marqué en
   échec et le suivant réessaie.

**Rattachement d'une présentation à sa fiche.** AMM GH cherche d'abord la fiche du pays : le
libellé exact (nom, puis alias), puis la même présentation écrite autrement (« OMEPRAL 20MG
GELULE B28 » = « OMEPRAL 20MG GEL B/28 »). Il ne cherche dans le reste du catalogue qu'ensuite.
Un spray n'est jamais les gouttes du même dosage, et deux boîtes différentes (B12 / B16) sont deux
présentations. Quand ces règles changent (1.1.3), le passage suivant relit tout le registre une
fois, comme au premier passage.

Côté Nextcloud, AMM GH ne fait que lire : des requêtes `PROPFIND` (profondeur 0) et `GET`.

## Mise en service (une fois)

1. **Créer un mot de passe d'application.** Dans Nextcloud, avec le compte propriétaire du
   classement (`Alamine`) :
   1. Ouvrez **Paramètres personnels > Sécurité**.
   2. Dans « Appareils et sessions », donnez un nom, par exemple « AMM GH synchronisation ».
   3. Cliquez sur **Créer un mot de passe d'application** et copiez le mot de passe affiché.
2. **Le saisir dans Render.** Ouvrez le service `amm-innov-api`, puis **Environment** :
   - `NEXTCLOUD_APP_PASSWORD` : le mot de passe copié ;
   - `NEXTCLOUD_USER` : `Alamine`, si la variable n'existe pas déjà ;
   - `GHPL_SYNC_ROOT` : `ALAMINE NEXTCLOUD/AMM GHPL - CLASSEMENT GENERAL`, c'est-à-dire le
     chemin du dossier dans « Fichiers ».

   Enregistrez : Render redéploie le service, et le premier passage part dans les cinq minutes.
3. **Retirer l'accès au besoin.** Supprimez le mot de passe d'application dans Nextcloud (même
   page). La synchronisation s'arrête aussitôt, sans rien casser.

Le premier passage reprend tout le classement : environ 1 800 présentations et 3 700 pièces. Il
peut durer longtemps sur Render gratuit. Pendant ce temps, le service s'appelle lui-même toutes
les quatre minutes pour ne pas s'endormir en route. Les passages suivants ne traitent que ce
qui a changé.

## Réglages

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `NEXTCLOUD_URL` | `https://innovpharma.stellarixcloud.sn` | adresse du Nextcloud |
| `NEXTCLOUD_USER` | (vide) | compte qui voit le classement |
| `NEXTCLOUD_APP_PASSWORD` | (vide) | mot de passe d'application ; vide = synchronisation inactive |
| `GHPL_SYNC_ROOT` | `ALAMINE NEXTCLOUD/AMM GHPL - CLASSEMENT GENERAL` | dossier du classement |
| `GHPL_SYNC_REGISTRY` | `0_REGISTRE AMM GHPL.xlsx` | registre, à la racine du dossier |
| `GHPL_SYNC_MAX_FILES` | `80` | scans téléchargés par passage |
| `GHPL_SYNC_ENABLED` | `true` | `false` suspend la synchronisation |
