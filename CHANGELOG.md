# Changelog

Toutes les évolutions notables du projet sont consignées ici.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnement [SemVer](https://semver.org/lang/fr/).

## [Non publié]

## [1.3.9] — 2026-11-25

### Ajouté
Livraison continue : de l'étiquette à la production, avec l'approbation de Mohamed et sans
commande sur le serveur (`docs/livraison-continue.md`).

- **Workflow « Livraison »** (`.github/workflows/livraison.yml`), lancé par l'étiquette `vX.Y.Z` :
  1. *Vérifier* : l'étiquette, `backend/VERSION` et le CHANGELOG concordent, le commit est sur
     `main`, sa CI est verte et ses images existent ; la composition du serveur et ses scripts se
     lisent.
  2. *Images* : les images testées par la CI reçoivent le numéro de version (rien n'est
     reconstruit), rapport des vulnérabilités critiques et élevées (Trivy, sans blocage pour
     l'instant), version publiée dans les Releases GitHub avec ses notes.
  3. *Production* : attend l'approbation (environnement `production`), puis demande l'installation
     au serveur et affiche son résultat réel, au vert ou au rouge.
- **Agent de livraison du serveur** (`scripts/serveur/livrer.sh`, minuteur systemd posé par
  `scripts/serveur/installer_livraison.sh`). Le serveur n'étant joignable que par le VPN, c'est lui
  qui vient chercher chaque minute la version approuvée. Avant d'installer, il vérifie que la
  demande vient du workflow, que l'étiquette est sur `main` et pointe sur le commit annoncé,
  qu'aucun fichier n'a été modifié à la main, et attend la fin d'une commande d'administration en
  cours (`relire_congo` …). Puis : sauvegarde chiffrée et vérifiée de la base (rien n'est installé
  si elle échoue), étiquette et images de la version (`TAG=X.Y.Z`, plus `latest`), démarrage,
  contrôle de santé de l'API avec le numéro attendu, et retour automatique à la version d'avant
  si elle démarre mal.
- Le jeton GitHub du serveur (droit « Deployments » sur ce seul dépôt) est rangé par
  `configurer.sh GITHUB_DEPLOY_TOKEN` dans `.env.livraison`, lu par l'agent seul : jamais dans
  `.env`, que lisent les conteneurs.

### Retiré
- L'ancien workflow « Deploy » (SSH vers `/opt/amm-innov`) : jamais utilisé, il ne pouvait pas
  joindre un serveur derrière le VPN.

## [1.3.8] — 2026-11-20

### Corrigé
Relecture du Congo : ce que l'essai du 20/11/2026 sur les pages 1 à 20 du classeur a montré.
L'essai ne faisait que lire : aucune fiche n'a été modifiée.

- **Un Code coupé après « …/24 » ou « …/3 ».** Un point lu comme une virgule (« 24,02.1 »)
  terminait la référence : « RVC-PSM-GM/24.02.1 B/N°4 LOPHS10 » devenait « RVC-PSM-GM/24 ».
  Une virgule entre deux chiffres est maintenant lue comme un point.
- **Les parties fixes du Code déformées par la lecture.** Quand la référence est lue en entier
  (« /3.03.1 B/N°3 … HS8 »), ce qui la précède ne peut être que « VC-PSM-GM » ou
  « RVC-PSM-GM » : « VORSM-ÈM », « VE-PSA-GM » et « RVC-PSM-6M » sont redressés. Le sigle du
  signataire est rapproché des sigles connus quand une seule lettre en diffère (« TMPHS12 »
  pour « JMPHS12 »). Les chiffres, eux, ne sont jamais devinés.
- **Un Code lu en partie n'est plus proposé.** Il est affiché (« CODE LU EN PARTIE ») pour
  être relevé sur le papier, et le numéro saisi reste.

### Modifié
- **Une lecture qui contredit la saisie attend le papier.** La relecture marque « À VOIR SUR
  LE PAPIER » une période quand le Code lu diffère d'un Code entier déjà saisi (la saisie
  prime sur l'OCR), quand il diffère de peu du numéro saisi (un chiffre mal lu d'un côté ou de
  l'autre), ou quand la décision scannée couvre d'autres années, au début comme à la fin, que
  la période enregistrée (origine 2014 → 2018 dont le scan est la décision 2018 → 2022 : le
  scan est peut-être celui d'une autre période). Ces périodes ne sont pas écrites par
  `--appliquer`, sauf avec `--avec-douteuses`.
- **La date butoir fait foi.** Une seule année fausse est une faute de saisie (fin 2025 saisie
  pour 2024) : elle est corrigée d'après la décision, sans attendre. Un jour qui passe au
  28 février dans la même année reste aussi une correction sûre.
- `--appliquer --pages 14-20` n'écrit que ces pages du rapport.

## [1.3.7] — 2026-11-19

### Corrigé
Trois défauts de la relecture du Congo (1.3.6), vus à son premier essai sur le serveur le
19/11/2026. L'essai ne faisait que lire : aucune fiche n'a été modifiée.

- **Le Code restait « illisible » sur les décisions de 2022.** Ces PDF portent déjà un texte,
  posé par le scanner, et l'application s'en contentait sans relire l'image. Or ce texte
  déforme justement la ligne surlignée (« Code RVC -PS,tÂ - GfA / 09.03.3 B/N" 1 JMPH512 »)
  ou l'omet. Les premières pages d'un PDF qui portent du surligneur sont maintenant lues sur
  l'image, et notre lecture passe avant celle du scanner, qui ne fait que la compléter.
- **Des dates recalculées à tort sur les anciens modèles.** Sans la clause « date butoir », la
  relecture partait de la date du scan : une origine déjà juste (28/02/2013 → 28/02/2017)
  était proposée 2017 → 2021. Sans la clause, les années connues ne bougent plus : seul le jour
  passe au 28 février.
- **La relecture ne suivait pas l'ordre du classeur** (tri par nom au lieu de gamme puis nom) :
  elle suit maintenant ses pages et affiche leurs numéros. `--pages 1-20` remplace `--limite`.
- **Fautes de lecture reprises dans l'écriture du Code** : « N? 4 », « N®° 1 » et « N°L » pour
  « N°4 » et « N°1 », « 02.245 » pour « 02.24.5 », « GM Y27.06.2 » pour « GM/27.06.2 » ; les
  écritures « 02.24.5 - B/N°1 » et « 27.06.2.B/N°1 » donnent la même forme « … B/N°1 ». Deux
  numéros qui ne diffèrent que par la ponctuation ne sont plus comptés comme différents.
- Chaque ligne du rapport dit d'où vient le texte (« lu sur l'image » ou « texte du PDF »).

## [1.3.6] — 2026-11-19

### Corrigé
- **Congo : le numéro d'AMM et les dates lus sur les décisions étaient faux.** Règles données
  par l'archiviste, classeur papier en main (19/11/2026), et relevées sur ses pages vérifiées :
  - **Le numéro d'AMM est le « Code » de l'article 2** (« Les références de l'autorisation de
    mise sur le marché sont : Code : VC-PSM-GM /27.06.2 B/N°7 JMPHS16 », « RVC-… » pour un
    renouvellement), jamais le numéro de la décision imprimé en tête (« DECISION N° 26-0466 »),
    que l'application prenait jusqu'ici. Le code de l'AMM d'origine qu'un renouvellement
    rappelle à son article 3 (« dont le code produit est … ») n'est pas pris pour le sien : il
    sert à retrouver l'origine. Code illisible : le numéro reste vide, à relever sur le papier,
    plutôt qu'un faux numéro.
  - **Toute période va d'un 28 février à un 28 février, quatre ans plus tard.** La date de fin
    est le 28 février de l'année écrite après « sera renouvelée en » (« date butoir du
    28 février ») ; la date de début, le 28 février quatre ans plus tôt, quelle que soit la
    date de signature, qui reste la date de la décision. L'application faisait courir la
    période de la date de signature (03/08/2026 → 03/08/2030 au lieu de 28/02/2026 →
    28/02/2030).
- **Une ligne surlignée n'était pas lue.** Sur le papier, le Code est passé au surligneur ; la
  lecture automatique sépare l'encre du papier par un seuil, et une mention imprimée en rouge
  sous un aplat orange disparaissait. Une page qui porte du surligneur est maintenant lue une
  seconde fois sans sa couleur, et les lignes que seule cette lecture a vues sont ajoutées à
  leur place. Mesuré sur deux décisions réelles : ligne du Code absente avant, lue après ; une
  page sans surligneur n'est pas relue (aucun temps perdu).

### Ajouté
- **Relecture des décisions du Congo déjà rangées** (`manage.py relire_congo`), en deux temps
  pour qu'un humain valide avant toute écriture :
  1. sans option, chaque décision est relue avec ces règles et la commande écrit, fiche par
     fiche et dans l'ordre du classeur, ce qui changerait (numéro, début, fin) ; rien n'est
     modifié ;
  2. `--appliquer` écrit les propositions du rapport. Une page déjà vérifiée sur le classeur
     papier n'est pas touchée (`--avec-verifiees` pour l'inclure), une valeur corrigée à la
     main entre-temps est laissée, et chaque écriture garde son motif dans l'historique.
  Une période sans scan ne reçoit que la règle des dates. Un numéro saisi avec d'autres espaces
  (« VC-PSM-GM /12.09.1 B/Nº3 ») n'est pas compté comme une différence.

### À savoir
- La lecture d'un Code peut encore se tromper d'une lettre sur un scan de mauvaise qualité
  (« IMPHS16 » pour « JMPHS16 » sur une capture basse résolution) : la liste avant / après se
  relit avant d'appliquer, et la vérification page par page reste la règle.

## [1.3.5] — 2026-11-18

### Modifié
- **Les scans sont servis par nginx : l'API n'en vérifie plus que le droit de lecture.** Jusqu'ici
  chaque scan affiché ou téléchargé faisait le trajet stockage → Python → navigateur. L'API
  répond maintenant sans corps et remet à nginx une adresse signée du stockage, valable deux
  minutes ; nginx va chercher le fichier et l'envoie. Scans, pièces de dépôt, fichiers d'un
  dossier importé et classeurs préparés sont concernés.
  - Rien ne change pour le navigateur : même adresse, mêmes droits, mêmes en-têtes (type, nom
    du fichier, cache, CORS, `nosniff`, `Content-Security-Policy: sandbox` des dossiers). Il ne
    voit jamais l'adresse du stockage, et l'emplacement nginx ne peut pas être appelé de
    l'extérieur. Un scan absent reste un 410, un stockage en panne un 503, décidés avant nginx.
  - nginx sait envoyer un morceau de fichier (`Range`) : un long scan pourra être lu page par
    page au lieu d'être téléchargé en entier.
  - Le stockage est lu en HTTPS avec certificat vérifié, et les adresses sont signées en V4, la
    seule signature que Cloudflare R2 accepte.
  - Retour arrière sans redéployer : `DOCUMENT_ACCEL_REDIRECT=0` puis `compose.sh up -d` ; l'API
    renvoie alors les scans elle-même, bloc par bloc, comme en 1.3.4. Le réglage est coupé par
    défaut hors de Docker Compose (Render, développement).

### Corrigé
- **Scans CamScanner refusés à l'import (« PDF refusé : actions actives ou fichiers incorporés
  détectés »).** CamScanner, très utilisé par les pays, ajoute sur chaque page un lien « Scanned
  with CamScanner » ; le contrôle de sécurité refusait toute action, donc la décision entière
  (constaté le 18/11/2026 sur le renouvellement de LITACOLD SINUS, Côte d'Ivoire). Les liens web
  simples sont maintenant retirés des pages avant le contrôle ; les images ne sont pas touchées
  et un PDF sans lien est conservé octet pour octet. Tout le reste est toujours refusé :
  JavaScript, lancement de programme, fichiers joints, formulaires, et un lien web suivi d'une
  autre action.
- **Chaque demande de scan reconstruisait la connexion au stockage.** La bibliothèque de
  stockage garde une connexion par fil d'exécution, et le serveur donne un fil neuf à chaque
  requête : 80 ms de processeur et 7 Mo perdus par scan, avant même de lire le fichier. Mesuré
  sur 80 demandes simultanées par huit, sans aucun fichier envoyé : 16 secondes et 370 Mo de
  mémoire. Avec un seul client partagé par processus : 0,9 seconde et 165 Mo.

### Mesuré
- Essai de bout en bout avec le nginx réel de l'image (1.27), l'API lancée comme en production
  et un stockage S3 d'essai : 880 scans de 1 à 15 Mo dont 30 % abandonnés en route. Mémoire de
  l'API : 166 Mo, plate du début à la fin (225 Mo en 1.3.4 sur le même banc ; 459 Mo en 1.3.3
  sur l'essai de la 1.3.4, dépôts compris) ;
  80 scans en 3,0 secondes au lieu de 4,6 à 5,5 ; nginx occupe 10 Mo et n'écrit rien sur disque.
- Fichier reçu identique à l'octet près (nom avec espace et accent), lecture partielle exacte,
  signature recalculée valide à partir de ce que nginx demande réellement au stockage, jeton de
  l'utilisateur et cookies non transmis au stockage, certificat non reconnu refusé.
- Non essayé ici, à contrôler à la mise en service : le vrai Cloudflare R2.

## [1.3.4] — 2026-11-18

### Corrigé
- **Application lente, puis indisponible, au fil de la journée : la mémoire de l'API montait
  sans redescendre.** Mesuré le 18/11/2026 sur le serveur, 19 heures après un démarrage : 456 et
  609 Mo pour les deux processus de l'API (150 Mo chacun au départ), limite de 1 Go atteinte
  2 014 fois. Sur Render, où la limite était de 512 Mo pour l'API et le worker réunis, c'est la
  cause la plus probable des chutes du 17/11.
  - Chaque scan affiché ou téléchargé repassait tout entier par la mémoire de l'API : sous le
    serveur ASGI, Django lit un fichier en entier avant d'en envoyer le premier octet, ici en
    blocs de 4 Ko (3 840 blocs pour un scan de 15 Mo). Les scans, les pièces de dépôt, les
    fichiers d'un dossier importé et les classeurs préparés sont maintenant envoyés bloc par
    bloc (256 Ko). Un scan abandonné en route (page tournée) n'est plus lu jusqu'au bout.
  - La mémoire libérée n'était pas rendue au système : le serveur web travaille sur une
    vingtaine de fils et, par défaut, garde une réserve par fil. Il est maintenant lancé avec
    deux réserves au plus et rend tout bloc de 128 Ko ou plus dès sa libération
    (`MALLOC_ARENA_MAX`, `MALLOC_MMAP_THRESHOLD_`, réglables).
  - Même charge rejouée avant et après (880 scans de 1 à 15 Mo dont 30 % abandonnés, 48 PDF
    de 8 Mo déposés, un seul processus) : 459 Mo et encore en hausse avant ; 251 Mo stables
    après. La correction seule donne 364 Mo, les réglages seuls 372 Mo : il faut les deux.
  - Sur le serveur, la limite de l'API a été portée de 1 à 2 Go le 18/11
    (`AMM_MEM_BACKEND=2g`), le temps de livrer cette version.

## [1.3.3] — 2026-11-16

### Corrigé
- **Classeur numérique : fiches qui tremblent, texte minuscule ou coupé selon la taille de la
  fenêtre** (les utilisateurs zoomaient ou dézoomaient pour « arranger » l'affichage).
  - La réduction d'une fiche trop haute se calculait sur une seule mesure : réduire la fiche
    l'élargit, donc change sa hauteur, donc change la réduction. Sur beaucoup de fenêtres (dont
    1366 × 768, la plus courante sur portable), la fiche passait sans fin d'une taille à l'autre.
    L'échelle est maintenant cherchée d'un coup, par essais successifs, et ne bouge plus.
    Avant, 11 des tailles de fenêtre essayées oscillaient ; après, sur 40 tailles mesurées,
    aucune n'oscille et aucun contenu n'est coupé.
  - Sur une fenêtre basse, le classeur garde une hauteur lisible et c'est la page qui défile,
    au lieu de rapetisser les fiches jusqu'à 55 %. Une fiche n'est plus réduite au-delà de
    70 % ; si elle ne tient toujours pas, elle défile : rien n'est coupé.
  - Les onglets des gammes s'adaptent à la hauteur du classeur et ne dépassent plus sous la
    couverture ; sur une fenêtre étroite, les commandes passent ensemble sous le titre au lieu
    de l'écraser.

## [1.3.2] — 2026-11-16

### Corrigé
- **Erreur 500 en supprimant une fiche rangée par un import de dossier** (« Supprimer la page »
  d'un classeur, ou suppression d'une AMM). L'import de dossier, ses fichiers source et sa
  traçabilité protègent la fiche, son renouvellement et son scan ; la corbeille devait les
  emporter avec elle, mais les rassemblait d'un seul coup, tous modèles mélangés, ce que Django
  refuse. Ils partent maintenant à la corbeille par étapes, ceux qui protègent d'abord, dans une
  seule entrée, et reviennent ensemble à la restauration. Le défaut datait de la corbeille
  (1.2.2) et touchait toute fiche rattachée à un import de dossier ; rien n'était supprimé à
  moitié (l'erreur annulait tout). Vu en production le 16/11/2026.

## [1.3.1] — 2026-11-16

AMM GH en anglais, première étape (décision du 16/11/2026 : anglais pour tous les utilisateurs,
serveur compris, livré en plusieurs versions). Cette version traduit toute l'interface.

### Ajouté
- **Bouton FR / EN** dans la barre du haut (dans le menu du compte sur téléphone) et sur la
  page de connexion. La langue est gardée sur le compte (`language`, français par défaut) :
  l'utilisateur la retrouve sur tout appareil. Choisie sur la page de connexion, elle rejoint
  le compte dès la connexion.
- **Toute l'interface existe en anglais** : 1 335 textes dans chaque fichier de langue
  (`locales/fr.json`, `locales/en.json`). Aux 465 textes déjà sortis des écrans s'ajoutent
  870 textes qui étaient écrits en dur : classeurs, import de dossiers, imports Excel et
  synchronisation GHPL, dépôts, plan d'action, fiche et frise d'une AMM, documents, audit,
  permissions, corbeille, journal des erreurs. Suivent aussi la langue : les messages de
  validation des formulaires, les textes des tableaux et de la pagination, le calendrier, les
  durées (« 3 ans et 2 mois », “3 years and 2 months”), l'attribut `lang` de la page. Les dates
  restent écrites JJ/MM/AAAA.
- API : `PATCH /api/v1/me` (la langue, et rien d'autre) ; `language` dans `/me`, la réponse de
  connexion et les comptes. L'interface envoie sa langue au serveur (`Accept-Language`).
- Un test garantit que les deux fichiers de langue ont les mêmes clés et les mêmes variables.

### Modifié
- Accords au singulier corrigés au passage en français : « 1 classeur » (au lieu de
  « 1 classeurs »), « 1 an », « Chronologie de la décision de… ».

### Reste en français pour l'instant
- Les textes que fabrique le serveur : libellés et conseils du plan d'action, questions et
  constats d'import, états de synchronisation, notifications, messages d'erreur du serveur,
  classeurs PDF, exports Excel. Les noms de pays aussi. Versions suivantes.

## [1.3.0] — 2026-11-15

Palier : AMM GH prête à quitter Render pour le Serveur 01 Stellarix, l'interface restant sur
Cloudflare Pages. Validation, déploiement et retour arrière : `docs/palier-1.3.0.md`.

### Ajouté
- **Sauvegarde chiffrée et vérifiée de la base sur le serveur**, chaque nuit
  (`scripts/serveur/sauvegarder.sh`) : `pg_dump` chiffré au vol (aucune copie en clair sur le
  disque, refus sans phrase secrète), puis essai de restauration du fichier chiffré dans une
  base d'essai avant de le compter comme sauvegarde. Même format que les sauvegardes de Render.
- **Copie hors de la machine** : chaque heure, le worker envoie les sauvegardes vérifiées dans
  le stockage des scans (S3), sous `sauvegardes/base/`, contrôle la taille reçue et applique la
  rétention (30 jours, jamais les 7 dernières).
- **Surveillance des sauvegardes** : un avertissement dans l'application à chaque CEO si la
  sauvegarde échoue, ne tourne plus depuis 30 heures ou n'est plus copiée hors machine ; deux
  contrôles d'intégrité (`backup_verified`, `backup_offsite`). Inactif sur Render.
- `scripts/serveur/configurer.sh` : règle `.env` sans l'éditer ; un secret est toujours saisi
  au clavier, masqué, jamais sur la ligne de commande. La phrase secrète des sauvegardes va
  dans `.env.sauvegarde`, lu par le seul service de sauvegarde.
- `scripts/serveur/brancher_interface.sh` : autorise l'interface Cloudflare Pages sur l'API
  du serveur (origines, liens des notifications, cookie de session entre deux adresses), avec
  contrôle de la réponse de l'API ; `--retirer` fait l'inverse.

### Corrigé
- **Classeur avec décisions officielles sur Ubuntu 26.04** : ce système confine `qpdf`
  (profil AppArmor), qui ne lit plus que des fichiers `.pdf`, `.qdf` et `.json`. La copie de
  travail d'un scan PDF s'appelait `.src` et la liste des pages passait par un fichier
  d'arguments : les deux lui étaient refusés et la préparation du classeur échouait. Les
  fichiers remis à `qpdf` se terminent tous par `.pdf` et la liste des pages passe en ligne de
  commande. Vu par la CI, dont les machines sont passées à Ubuntu 26.04 le 15/11/2026 ; la
  production (image Debian, sans ce confinement) n'était pas touchée.

### Modifié
- `docker-compose.prod.yml` : le script lancé chaque nuit par le service `backup` se choisit
  par `BACKUP_SCRIPT` (inchangé par défaut). `docker-compose.partage.yml` : le worker lit le
  dossier des sauvegardes en lecture seule.
- `docs/deploiement-serveur-partage.md` : sauvegardes, et bascule depuis Render pas à pas.

## [1.2.9] — 2026-11-14

Suite de l'essai sur le Serveur 01 Stellarix : essai privé réussi le 14/11 (copie de la base
du 13/11, 1 860 AMM, temps réel actif), ouverture publique préparée.

### Ajouté
- `scripts/serveur/ouvrir_public.sh` : ouvre AMM GH sur son adresse HTTPS à travers le Caddy
  déjà en place sur la machine (celui de JUSTI GH), ou la referme (`--fermer`). Le portier
  est testé avant d'être touché, sa configuration validée avant d'être rechargée, et tout
  refus laisse le voisin exactement comme avant.

### Corrigé
- **Contrôle de santé de l'image d'interface** : il interrogeait `localhost`, résolu en IPv6
  sur certaines machines alors que nginx n'écoute qu'en IPv4. Le conteneur était marqué
  « unhealthy » alors que l'application répondait. Il interroge `127.0.0.1`.
- `docs/deploiement-serveur-partage.md` : les fichiers d'exploitation de JUSTI GH ne sont pas
  remplacés à chaque livraison (seules les images le sont) ; l'ouverture publique se fait
  par le script ci-dessus.

## [1.2.8] — 2026-11-13

Deuxième écart du rapport d'architecture (hébergement) : essai d'AMM GH sur le Serveur 01
Stellarix, à côté de JUSTI GH. Render reste la production pendant l'essai.

### Ajouté
- **Installation sur un serveur partagé** (`docker-compose.partage.yml`,
  `docs/deploiement-serveur-partage.md`) : AMM GH tourne sans Caddy ni Grafana propres, sans
  port public (nginx sur `127.0.0.1:8081`), mémoire plafonnée par service, projet Compose
  `amm-gh` distinct des voisins.
- `scripts/serveur/preparer_env.sh` (fichier `.env` avec des secrets tirés au hasard sur
  place), `scripts/serveur/restaurer_base.sh` (restaure une sauvegarde chiffrée dans la base du
  serveur ; refuse une base déjà remplie sans `--remplacer`), `scripts/serveur/compose.sh`.

### Corrigé
- **Image de l'interface (nginx)** : derrière un relais qui termine TLS (Caddy), Django se
  croyait en clair, car nginx remplaçait `X-Forwarded-Proto` par « http » : les liens de
  l'API partaient en `http://`. Le protocole du relais est maintenant transmis, ainsi que le
  port de l'adresse demandée (`Host`).
- `docker-compose.prod.yml` : PostgreSQL 18 (les sauvegardes sont écrites par `pg_dump` 18,
  qu'un serveur 16 ne relit pas), volume monté sous `/var/lib/postgresql`.

### Modifié
- `docs/deploiement-render.md` : sur macOS, décompresser un artefact avec `ditto`.

## [1.2.7] — 2026-11-13

Premier écart du rapport d'architecture (ISO 25010, fiabilité : récupérabilité) : une
sauvegarde n'est fiable que si elle a été restaurée.

### Ajouté
- **Restauration d'essai de chaque sauvegarde chiffrée.** Après le chiffrement, le workflow
  « Base Render » déchiffre la sauvegarde, la restaure dans une base PostgreSQL jetable et
  contrôle son contenu (tables, migrations, fiches AMM, produits, pays, comptes). Si elle ne se
  relit pas, l'exécution passe au rouge et GitHub prévient par e-mail. Aucun chiffre métier
  n'est écrit dans le journal, qui est public.
- `scripts/verify_backup.sh <sauvegarde.dump.gpg>` : le même essai sur un poste, avec Docker
  pour seul outil. La phrase secrète est demandée au clavier ; rien n'est écrit sur le disque
  ni dans la base de production.

### Modifié
- `docs/deploiement-render.md` : sauvegardes chiffrées, essai de restauration, restauration
  réelle.

## [1.2.6] — 2026-11-12

Rangements et suppressions idempotents, et un plan d'action pour agir vite sur les fiches
incomplètes. Chaque AMM est traitée pour elle-même, sans la comparer à une autre.

### Ajouté
- **Plan d'action** (menu, juste sous le Dashboard ; aussi en carte sur le Dashboard Afrique
  et le Dashboard pays). Les AMM à compléter, par manque : **origine non identifiée** (n° ou
  date d'origine absents), **sans renouvellement** (origine échue, aucun renouvellement
  enregistré), **renouvellement à déposer** (expirée ou à renouveler, rien en cours),
  **décision d'origine sans scan**, **renouvellement sans scan**. Les plus urgentes d'abord ;
  chaque ligne mène à l'onglet de la fiche qui corrige le manque. Filtre pays.
- **Filtre « Manque » de la liste des AMM** (`?gap=no_original`, `missing_renewal`,
  `to_file`, `original_scan`, `renewal_scan`) : le plan d'action y renvoie pour la liste
  complète, exportable.
- API : `GET /api/v1/amms/action-plan`, filtre `gap` sur `/api/v1/amms`, champ
  `status_reason` des imports de dossiers.

### Modifié
- **Suppressions immédiates et sans erreur.** Gammes, règles d'alerte, scans, pièces de dépôt :
  plus de boîte de confirmation ; l'élément part à la corbeille et « Annuler » le remet
  aussitôt (pour qui peut restaurer). Supprimer deux fois (double clic, onglet en retard) ne
  montre plus jamais d'erreur : AMM, produits, pays, gammes, règles, renouvellements, scans,
  pièces, pages et passages du classeur répondent « déjà fait ». La désactivation d'un compte
  garde sa confirmation. L'annulation d'un renouvellement garde la sienne (ses scans sont
  archivés).
- **Ce qui est supprimé ne revient pas par un import.** Une AMM mise à la corbeille (depuis la
  liste, la fiche ou le classeur) n'est recréée ni par l'import Excel, ni par le registre GHPL,
  ni par les scans classés, ni par un dossier pays : la ligne est notée « supprimée (à la
  corbeille) », le dossier pose la question « restaurez-la si elle existe bien ». Restaurée,
  elle est de nouveau suivie.
- **Rangement : rangé, ou la raison est dite.** Un dossier analysé mais pas rangé dit
  pourquoi, sur sa page, dans l'historique et le récapitulatif (fiche changée pendant
  l'analyse, accès au pays, preuve manquante, rangement automatique désactivé, en file
  d'attente…), au lieu de « relancez l'analyse ». Un échec inattendu est noté dans le journal
  des erreurs.
- **Rangement par ordre d'urgence** : les dossiers en attente sont rangés AMM expirées
  d'abord, puis à renouveler, puis valides (échéance la plus proche devant), à égalité le plus
  ancien dépôt.

### Retiré
- `backend/apps/imports/dump.rdb`, instantané Redis de test versionné par erreur (`*.rdb`
  ignoré désormais).

## [1.2.5] — 2026-11-11

Suite de l'audit d'infrastructure du 11/11/2026 (constats moyens et à vérifier), et rangement
des AMM par l'import de dossiers et la synchronisation GHPL. Audit :
(`docs/audit-infrastructure-1.2.4.md`). Les constats critique et hauts sont réglés (1.2.4 et
gestes dans les comptes : 55 copies de la base supprimées, Worker Cloudflare de réveil créé).

### Ajouté
- **Journal des erreurs** (Administration › Erreurs, CEO ; droit `errors.view` réglable).
  Les erreurs du serveur, des tâches de fond et de l'interface sont gardées dans AMM GH, sans
  service externe : type, message, pile, page ou tâche, version, dernier utilisateur. La même
  erreur se compte au lieu de se répéter ; résolue, elle se rouvre si elle revient. L'interface
  envoie ses erreurs d'affichage (dix par session au plus, jamais ce qui a été saisi).
- **Surveillance de Redis** (25 Mo gratuits, sans éviction) : contrôle d'intégrité et, à 80 %,
  un avertissement dans l'application au CEO, une fois par jour au plus.

### Corrigé
- **Import de dossiers : plan du classement AMM GHPL.** Un dossier du classement (« METRO-GH »
  déposé seul) était découpé en un import par rubrique (« … - 1_AMM ORIGINE - 2016 - N° … »,
  « … - 4_DEPOTS - COURRIERS »), et « COURRIERS » ou « 1_AMM ORIGINE » étaient pris pour le
  nom du produit. Les rubriques (`1_AMM ORIGINE`, `2_RENOUVELLEMENTS`, `3_VARIATIONS`,
  `4_DEPOTS`, `5_RCP`, dossiers d'année) restent maintenant dans leur présentation : un import
  par présentation, avec son vrai nom. Les copies (`_DOUBLONS`, `_PAGES SEPAREES`,
  `_DOCUMENT COMPLET`) ne sont plus envoyées.
- **Import de dossiers : pays retrouvé par le produit et le n° d'AMM** quand ni le dossier ni
  un scan lisible ne le donnent (« N° E-2015-2001 » d'une AMM ivoirienne suivie de ce
  produit). Deux critères, jamais le n° seul. Les dossiers restés en question sont relus d'eux-
  mêmes après la mise à jour.
- **Synchronisation GHPL** : les lignes du registre qui désignent un dossier et non une pièce
  ne sont plus « laissées de côté (format sans extension) ».

### Modifié
- **Renouvellement de la base de nuit seulement** (0 h - 7 h à Dakar) tant qu'elle a moins de
  28 jours : il redéploie l'API et tombait en pleine journée, GitHub retardant ses tâches
  planifiées de plusieurs heures. Une vérification horaire le lance dans la fenêtre.
- **E-mails d'alerte, de rappel et digest hebdomadaire coupés** par défaut
  (`ALERT_EMAILS_ENABLED`), conformément à la décision « alertes dans l'application
  seulement » ; ils partaient dès qu'`EMAIL_URL` était renseigné. Les alertes et rappels restent
  dans l'application.

## [1.2.4] — 2026-11-11

Corrective issue de l'audit d'infrastructure du 11/11/2026 (`docs/audit-infrastructure-1.2.4.md`).

### Sécurité
- **Sauvegardes de la base chiffrées.** Le dépôt est public : le workflow « Base Render »
  publiait chaque jour une copie complète de la base en artefact, lisible par tout compte
  GitHub. Les copies sont maintenant chiffrées (AES-256, secret `BACKUP_PASSPHRASE`) et gardées
  30 jours ; sans ce secret, rien n'est publié. Les anciens artefacts sont à supprimer à la main.
- `/metrics` n'est plus public en production sans `METRICS_TOKEN` (404).

### Corrigé
- **Classeurs lisibles sur les petits écrans.** Sur écran large, la feuille s'étale sur les deux
  pages du classeur ouvert : identité, cartes et situation à gauche, vérification et constat à
  droite. Chaque moitié est beaucoup moins réduite qu'une feuille entière (navigateur de
  1280 × 585 px, un écran 1280 × 720 : réduction 0,66 et 0,85 au lieu de 0,55, et le bas de la
  feuille n'était plus visible). Pendant que
  la page tourne, et sur téléphone, la feuille reste sur une seule page.
- CI : l'installation de `qpdf` est bornée (6 min, trois essais) et ne bloque plus la CI quand
  le miroir Ubuntu ne répond pas ; sans qpdf, seul le test d'assemblage des classeurs est sauté.
- **Après un déploiement, un onglet resté ouvert se recharge seul** au lieu d'afficher
  « Unexpected Application Error » (fichier de l'ancienne version demandé à Cloudflare). Toute
  autre erreur d'affichage montre un message clair, avec le menu, « Recharger » et « Accueil ».
- **Worker Celery surveillé** (Render, conteneur unique) : s'il s'arrête, il est relancé
  (5 s, puis jusqu'à 60 s) au lieu de laisser imports et rappels en attente jusqu'au
  prochain redémarrage.
- **Sonde de santé Render sur `/api/v1/health/live`** : une base ou un Redis lents ne font plus
  redémarrer une API saine.

### Ajouté
- Réveil de l'API par un Worker Cloudflare toutes les 5 minutes
  (`scripts/cloudflare/keepalive-worker.js`) : le réveil GitHub Actions ne partait que 3 à 7
  fois par jour au lieu de 144. Il reste en secours.

## [1.2.3] — 2026-11-10

### Ajouté
- **Audit et traçabilité** (Administration > Audit, CEO et siège). Qui a fait quoi, quand,
  dans toute l'application : créations, modifications (champ par champ, avant → après),
  connexions, mises à la corbeille (avec les éléments liés) et restaurations. Filtres par
  personne, action, type, pays et période. Rien n'est saisi pour l'audit : il relit
  l'historique et la corbeille.
- **Permissions** (Administration > Permissions, CEO seul). Un tableau rôles × actions : le CEO
  coche ce que le siège et les pays peuvent faire (classeurs, référentiels, fusion de produits,
  retrait d'un scan, règles d'alerte, pièces demandées, corbeille, audit). Les droits viennent
  de la base, en partant des réglages d'avant ; chaque changement est tracé dans l'audit. Le
  CEO garde toujours tous les droits et lui seul règle les permissions : personne ne peut
  s'enfermer dehors. Un droit accordé à un rôle pays reste limité à ses pays (corbeille,
  audit).
- Historique des comptes utilisateurs (création, modification, désactivation, connexions),
  sans le mot de passe.

### Modifié
- Les boutons des référentiels (produits, gammes), de fusion et de retrait d'un scan suivent
  les permissions au lieu du rôle. La gamme se supprime avec le droit « Gérer pays, gammes et
  produits » (avant : CEO seul dans l'interface, alors que l'API l'acceptait du siège).

## [1.2.2] — 2026-11-10

### Ajouté
- **Corbeille** (Administration > Corbeille, CEO et siège). Plus rien n'est effacé dans AMM
  GH : ce qu'on supprime part à la corbeille avec tout ce qui partait avec lui (une fiche AMM
  avec ses renouvellements, scans, pièces, alertes et imports de dossiers), et se restaure à
  l'identique, en un clic. La corbeille n'est jamais vidée : une entrée restaurée reste,
  marquée « restaurée » (qui, quand). Vont à la corbeille : fiche AMM, page du classeur,
  passage, renouvellement annulé, page en trop, pièce et échantillon d'un dossier de dépôt
  (le fichier est gardé), pays, gamme, produit, règle d'alerte, type de pièce.

### Modifié
- **Classeurs : « Supprimer la page » est immédiat.** Plus de fenêtre ni de fiche à choisir
  pour reprendre les pièces : la page part à la corbeille avec ses scans, et « Annuler », dans
  le message qui suit, la restaure aussitôt. Les imports ne la recréent pas tant qu'elle n'est
  pas restaurée.
- **Utilisateurs : « Supprimer » désactive le compte** au lieu de l'effacer (il ne se connecte
  plus ; son historique reste attribué).
- Le contrôle d'intégrité ne compte pas les fichiers des éléments à la corbeille comme des
  fichiers orphelins.

## [1.2.1] — 2026-11-10

### Ajouté
- **Classeurs : « À imprimer ».** Pendant la lecture, une page dont le scan existe mais dont
  la feuille manque dans le classeur papier se marque « À imprimer » (bouton sur la page),
  puis « Imprimée et rangée ». Le bilan du classeur, l'étagère et le Dashboard comptent les
  AMM à imprimer, et le filtre « AMM à imprimer » les feuillette. Sans effet sur la
  conformité : un dossier peut être conforme avant d'être imprimé. Rien n'est supprimé :
  l'état change et l'historique le garde.
- **Classeurs : modifier le n° et les dates directement sur la carte** (crayon de la carte
  « AMM d'origine » ou « Dernier renouvellement », ou clic sur une valeur), avec
  « Enregistrer » et « Annuler » sur la carte, sans descendre jusqu'à « Corriger ».

### Modifié
- **Classeurs en lecture seule hors CEO et siège.** Les réglementaires pays consultent les
  classeurs (pages, chronologie, scans) sans pouvoir les modifier : ni constat, ni
  correction, ni scan, ni ajout de page. Le serveur refuse aussi ces écritures (droit
  `binder.edit`). Le téléchargement des classeurs reste réservé au siège et au CEO.
- **Classeur sans défilement.** La page du classeur tient dans la fenêtre (barre, classeur et
  feuilletage) ; une feuille trop remplie se réduit juste assez pour être vue en entière au
  lieu de défiler. Animation et son deviennent deux petits boutons.

### Sécurité
- Outils de test : Vitest 5 et jsdom 31. Les 2 alertes critiques de `npm audit` (Vitest 3)
  sont corrigées. En CI, les tests du frontend tournent sur Node 22 (le Fetch de Node 24 ne lit
  pas les envois multipart de jsdom) ; le build reste sur Node 24.

## [1.2.0] — 2026-11-10

Palier : fin de la remise en ordre de l'architecture commencée en 1.1.8 (revue
d'architecture du 09/11). Aucun changement de données ; un seul ajout visible pour l'API
(`actions` dans `/me`). Validation, déploiement et retour arrière : `docs/palier-1.2.0.md`.

### Modifié (architecture)
- **Plus aucun import qui remonte les couches.** Le test d'architecture n'a plus
  d'exception. Le catalogue (`catalog/extensions.py`) et la fiche AMM
  (`amm/extensions.py`) ouvrent des points d'extension que les apps du dessus remplissent :
  documents d'un pays ou d'un produit, fusion de produits, corrections des dossiers dans
  l'historique, points à vérifier dans la liste des AMM. `seed_demo` passe dans une app
  `apps.demo` (couche haute, aucune app ne l'importe).
- **Lecture des dossiers découpée par sujet.** `recognition.py` (1 066 lignes) devient un
  paquet : texte, dates, n°, titulaire, tableaux, recueils, fichiers. `preview.py`
  (1 195 lignes) sort ses briques dans `evidence.py` et `identification.py`.
- **Interface : gros écrans découpés.** Page du classeur, chronologie et étapes des
  dossiers de dépôt, un composant par fichier.
- **Droits lus depuis le backend.** `/me` et la connexion renvoient `actions`, les actions
  sensibles permises (`apps/accounts/roles.py`) ; l'interface les lit avec `useCan` au lieu
  de recopier les rôles. Premiers types du frontend dérivés du schéma OpenAPI.

### Sécurité
- **Dépendances Python figées** (`requirements.in` → `requirements.txt` par `pip-compile`) :
  la CI, Docker et Render installent exactement les mêmes versions (`docs/dependances.md`).
- **`pip-audit` sans aucune exception** : Twisted 26.10.0 corrige les 7 CVE ignorées
  jusqu'ici. `npm audit` : aucune vulnérabilité dans le code livré.

## [1.1.9] — 2026-11-09

### Modifié (architecture, sans changement visible)
Première étape SOLID de la revue d'architecture du 09/11. L'API, les écrans et les données ne
changent pas.
- **Le socle ne dépend plus du métier** (inversion des dépendances). `apps/core` n'importe plus
  aucune app : le rattrapage du travail en attente, les contrôles d'intégrité, la reprise au
  démarrage du worker, le maintien en éveil et les métriques sont déclarés par chaque app dans
  son `hooks.py` (`apps/core/registry.py`). La commande `check_integrity` et la tâche
  `recover_pending_work` font exactement les mêmes contrôles et rattrapages qu'avant.
- **Droits centralisés** (`apps/accounts/roles.py`). Les groupes de rôles et les actions
  sensibles des classeurs (supprimer un passage ou une page, renommer une page, retirer une
  pièce, télécharger) sont définis une seule fois ; le code demande `can()` / `ensure_can()`.
  Les listes recopiées dans les classeurs et les rappels ont disparu.
- **Classeurs : `layout.py` découpé** (responsabilité unique). La conformité et ses compteurs
  vont dans `binders/conformity.py`, avec un critère par classe (ouvert/fermé : ajouter un
  niveau de vérification = ajouter une classe) ; la chronologie affichée va dans
  `binders/timeline.py`.
- **Test d'architecture en CI** (`tests/test_architecture.py`) : trois couches (socle, métier,
  fonctions transverses) ; une app n'importe que sa couche ou celles du dessous, et `core`
  aucune. Les 8 écarts restants sont listés et seront corrigés dans le palier 1.2.0.

### Modifié
- Message de refus du renommage d'une page : « Seuls le CEO et le siège peuvent modifier le
  titre d'une page. »

## [1.1.8] — 2026-11-09

### Performances
- **Index de la base de données** (revue d'architecture du 09/11). La recherche de l'API
  (`?search=` des listes AMM, alertes et documents) passe par des index trigramme `pg_trgm` sur
  le nom du produit, ses alias, le n° d'AMM et le n° de renouvellement : Postgres ne relit plus
  toute la table à chaque frappe. S'y ajoutent des index pour le scan en vigueur d'une AMM, les
  renouvellements par étape, les alertes par statut et échéance, et les notifications d'un
  utilisateur (récentes, non lues).
- Les index sont créés sans bloquer l'application (`CREATE INDEX CONCURRENTLY`, opération
  `AddIndexOnline` dans `apps/core/db.py`) ; en développement sous SQLite, les index propres à
  Postgres sont ignorés. Aucun changement d'API ni d'écran.

## [1.1.7] — 2026-11-06

### Ajouté
- **Classeurs : supprimer une page** (siège et CEO). La fiche AMM disparaît de toute
  l'application : classeurs, fiche, alertes, rappels, tableaux de bord. Ses pièces (scans,
  récépissés) ne sont jamais perdues : une autre fiche du pays les reprend, à la période de même
  date. Les imports et la synchronisation ne recréent plus cette page ; « Ajouter une page » la
  fait revenir.
- **Classeurs : modifier le titre d'une page** (siège et CEO). Le nom de la présentation change
  partout, pour tous les pays qui la suivent ; l'ancien nom reste reconnu par les imports.
- **Chronologie : ignorer une interruption de validité.** Quand il n'y a pas eu de renouvellement
  sur une période, le trou reste visible mais ne compte plus comme un manque : on n'est plus
  obligé d'ajouter un passage qui n'existe pas.

### Modifié
- **Chronologie : supprimer un passage qui n'existe pas** (renouvellement saisi à tort ou en
  double, dépôt jamais fait), le plus récent ou un plus ancien, sans supprimer de scan : ses
  pièces sont rangées sur la période choisie (l'AMM d'origine par défaut), jamais archivées.
  Réservé au siège et au CEO. La numérotation des renouvellements est recalculée sans trou.
- **Page du classeur : plus de bloc « Dernier renouvellement » vide** quand l'AMM n'en a pas. En
  correction, il s'ouvre seulement si le papier porte un renouvellement (« Le papier porte un
  renouvellement »).

### Corrigé
- **Tests compatibles avec pypdf 7** (sorti le 05/11) : le test du PDF piégé par du JavaScript
  n'utilise plus `add_js`, retiré de pypdf. Le contrôle des PDF reçus n'avait pas à changer.

## [1.1.6] — 2026-11-05

### Ajouté
- **Imprimer un scan.** Un petit bouton « Imprimer » :
  - sur la miniature de la décision, dans les classeurs ;
  - à côté de « Télécharger » dans l'onglet Documents de la fiche AMM ;
  - dans la barre de la visionneuse (bibliothèque, chronologie, fiche).

  La boîte d'impression du navigateur s'ouvre sur le scan seul, sans quitter la page. Si le
  navigateur refuse, le scan s'ouvre dans un onglet pour être imprimé de là.

## [1.1.5] — 2026-11-04

### Modifié
- **Classeurs : les 4 niveaux de vérification d'un dossier.** Chaque page affiche « Vérification du
  dossier » :
  1. visible dans le classeur numérique (la fiche existe dans AMM GH) ;
  2. dossier papier dans le classeur (constat de l'archiviste) ;
  3. version scannée de la décision en vigueur (AMM GH) ;
  4. bonne date et bon n° d'AMM (relevés sur le papier, renseignés, inchangés depuis).

  Résultat : « Le dossier est conforme » quand les 4 sont justes, sinon « Dossier non conforme » avec
  le niveau en défaut. Le bouton « Conforme » devient « Papier conforme » : il dit que le papier est là
  et que la date et le n° sont justes, pas que tout le dossier l'est.
- Les constats déjà faits sont repris : une page tamponnée sans scan de la décision en vigueur, ou
  dont la fiche a changé depuis, est maintenant « non conforme ».

### Corrigé
- **Incohérences des compteurs des classeurs.** L'étagère comptait les décisions « à scanner »
  d'après l'état du dossier de la fiche, la page d'après le scan de la décision en vigueur : les
  chiffres ne correspondaient pas. Les pages modifiées depuis leur vérification restaient comptées
  « conformes » sur l'étagère. Tous les compteurs (étagère, Dashboard, page de garde, intercalaires,
  bilan, PDF, fiche AMM) viennent maintenant du même calcul que la page.
- Filtre « Écarts et manques » : il regarde la décision en vigueur (dernier renouvellement obtenu),
  plus seulement l'AMM d'origine.

### Sécurité
- follow-redirects 1.16.2 (dépendance d'axios) : faille GHSA-mrwp-f3q8-3g9p publiée le 03/11, des
  en-têtes d'identification pouvaient suivre une redirection.

## [1.1.4] — 2026-10-29

### Corrigé
- **Fusion d'une fiche en double refusée (erreur 500)** quand le libellé de la fiche était long
  (« DOLEX 75MG IM/IV SOL INJ AMP 3ML B/5 ») : le motif inscrit dans l'historique dépassait les
  100 caractères admis. Il est raccourci.
- Carte de synchronisation : toutes les fiches en double sont listées (les 40 premières seulement
  jusqu'ici, si bien que celles « à vérifier », en fin de liste, n'apparaissaient pas).

## [1.1.3] — 2026-10-29

### Corrigé
- **Fiches en double ouvertes par l'import du registre.** Une présentation connue par le seul
  classement (« Classement seul ») était parfois rattachée au produit d'un autre pays : une seconde
  fiche s'ouvrait à côté de celle du pays, sans scan, avec les mêmes dates et parfois le même dépôt
  (deux rappels). Exemple : « SALBUTUS 2MG-5ML SIROP-SUSP BUV 100ML » en Côte d'Ivoire, doublée
  d'une fiche au libellé du Sénégal. L'import cherche désormais d'abord la fiche du pays (libellé
  exact, puis même présentation écrite autrement), et seulement ensuite le reste du catalogue.
- **Présentations confondues.** Un spray n'est plus rattaché aux gouttes du même dosage
  (« NASO-GH 0,05% SPRAY » n'est pas « NASO GH 0.05% GTTE F/10ML ») ; deux boîtes différentes ne
  sont plus la même présentation (« SACHET B12 » / « SACH B/16 », « B100 » / « B/30 »).
- Le premier passage de la synchronisation après la mise à jour relit tout le registre avec ces
  règles : les présentations manquantes sont créées et leurs scans rangés sur la bonne fiche.

### Ajouté
- **Fiches en double** (Imports Excel, carte de synchronisation) : la synchronisation liste, pays
  par pays, les fiches qui suivent la même présentation que la fiche du pays sous le libellé d'un
  autre pays. Une simple copie (ni document, ni dossier, des dates et renouvellements identiques)
  se fusionne sur demande, sans rien perdre ; les autres sont listées « à vérifier » avec la
  différence trouvée.

## [1.1.2] — 2026-10-26

### Corrigé
- **Synchronisation AMM GHPL : décisions groupées.** Un même scan qui sert à plusieurs présentations
  (décision groupée, au Mali notamment) était déplacé d'une fiche à l'autre au lieu d'être présent
  sur chacune. Chaque fiche garde désormais sa copie. Un document n'est déplacé vers une autre fiche
  que si sa pièce a vraiment quitté la première dans le classement. Les fiches touchées au premier
  passage (26/10) retrouvent leur copie au passage suivant (réparation automatique).

### Sécurité
- CVE-2026-83813 (client DNS de Twisted, publiée le 27/10) ignorée par `pip-audit` avec son motif :
  AMM GH ne fait aucune résolution DNS par Twisted (daphne ne sert qu'en développement).

## [1.1.1] — 2026-10-26

### Corrigé
- Fiche AMM : une AMM expirée n'affiche plus deux fois « Expirée » dans l'en-tête (statut et urgence).
- Carte d'un renouvellement : les intitulés (« Date de décision »…) ne passent plus sur deux lignes
  quand la fenêtre est étroite (trois colonnes par ligne, six sur grand écran).

## [1.1.0] — 2026-10-26

### Ajouté
- **Synchronisation automatique avec le classement AMM GHPL** (`docs/synchronisation-ghpl.md`).
  Chaque heure, AMM GH relit le registre du classement sur Nextcloud, en lecture seule. Il
  réimporte les seules présentations qui ont changé (registre, puis scans classés) et range les
  pièces sur leur fiche :
  - un scan nouveau est téléchargé ;
  - un scan déjà envoyé est rattaché sans être retéléchargé ;
  - un scan reclassé dans le classement (autre période, type ou AMM) est suivi par son document,
    sans doublon ;
  - un document Word ou trop lourd est listé.

  Les dates corrigées dans AMM GH ne sont jamais réécrites : un écart est signalé « à vérifier ».
  Si le registre est incomplet (en cours d'écriture), rien n'est appliqué. Un passage manqué
  pendant que Render dormait est rattrapé au réveil. Un passage long garde le service éveillé.
  Carte « Synchronisation avec AMM GHPL » dans Imports Excel, avec « Synchroniser maintenant ».
  Mise en service : un mot de passe d'application Nextcloud à saisir dans Render
  (`NEXTCLOUD_APP_PASSWORD`).

## [1.0.9] — 2026-10-25

### Sécurité
- Interface : zod 4.6.7 (faille GHSA-mrhx-c7xc-m3w5 publiée après la fusion de la 1.0.8, qui
  bloquait la CI de main par `npm audit`).
- Serveur : cinq failles de Twisted publiées le 24/10 (IMAP, IRC, telnet, XML, serveur HTTP
  twisted.web) ignorées par `pip-audit`, avec leur motif dans la CI : Twisted n'arrive que par daphne
  (serveur de développement), la production est servie par uvicorn ; seul correctif : une préversion.

### Modifié
- Messages de validation des formulaires en français (« Champ obligatoire », « adresse e-mail
  invalide ») au lieu de l'anglais.

## [1.0.8] — 2026-10-23

### Ajouté
- **Nouveau calendrier** pour toutes les dates : on choisit l'année, puis le mois, puis le jour (ou on
  tape JJ/MM/AAAA), en français. Sous les dates d'une période, la validité se calcule toute seule
  (« Validité : 5 ans, jusqu'au 06/04/2021 ») et une durée différente de celle du pays est signalée.
- **Classeurs : la chronologie se corrige** (ce que la lecture automatique d'un scan a faussé). Dans la
  fenêtre Chronologie, pour chaque période (AMM d'origine, renouvellements) : ✎ corrige le n° et les
  dates (date de fin vide : recalculée), + ajoute une pièce directement sur cette période, à la date
  saisie, sans lecture automatique ; le dernier renouvellement se supprime (saisi à tort ou en double
  par un import) en rangeant ses pièces sur une autre période au lieu de les archiver. Chaque pièce
  (décision, récépissé…) se corrige : date, type, période ; le CEO ou le siège peut la retirer
  (archivée, l'historique la garde). L'AMM (statut, échéance, état du dossier) et la page du classeur
  se mettent à jour aussitôt. API : `PATCH|DELETE /binders/{clé}/pages/{amm}/periods/{origin|id}`,
  `POST /binders/{clé}/pages/{amm}/documents`, `PATCH|DELETE /binders/{clé}/pages/{amm}/documents/{id}`.

### Corrigé
- **Classeurs : « Corriger » ne remet plus d'anciennes valeurs.** Le formulaire gardait les valeurs du
  moment où la page avait été ouverte : après un scan rangé, l'enregistrer réécrivait les anciennes
  dates par-dessus les nouvelles. Il repart désormais des valeurs actuelles de la page.
- **Une date de début corrigée refait le calcul sur 5 ans** (durée de validité du pays) : classeurs,
  fiche AMM, renouvellements, création d'AMM et de page. Avant, une fin importée du Dashboard restait
  figée et la correction « ne changeait rien ». Une fin égale à début + durée reste calculée.
- Classeurs : la décision relevée sur le papier conclut le dépôt en cours au lieu de créer un second
  renouvellement (le tampon « DÉPOSÉ » restait) ; une décision plus ancienne que le dépôt prend sa
  place dans l'ordre des dates.
- Classeurs : un renouvellement rejeté ou abandonné ne compte plus de faux manques ; une
  interruption de validité après un renouvellement non daté est détectée ; une page dont la
  décision en vigueur n'est pas scannée le dit (et passe « À scanner ») au lieu de montrer le scan
  d'une autre période comme le sien.
- Alertes :
  - l'alerte DOSSIER se ferme quand le scan arrive ; un dépôt ne ferme plus DOSSIER ni J0 ;
  - une échéance corrigée remplace ses alertes au lieu de les dédoubler ;
  - une alerte DECISION n'est plus classée « Renouvellement obtenu » après un rejet ou un abandon ;
  - J-180 et J-90 tombent le jour du dépôt idéal et de la limite agence affichés ;
  - le motif de résolution s'affiche en clair.
- Durée restante : mois entiers, en années et mois (« 872 j (2 ans et 4 mois) » et non « 29 mois »).
- Tableau de bord : « expire sous 6 mois / 12 mois » compte comme le statut « À renouveler » en fin
  de mois.
- Export Excel : les colonnes RENOUV. donnent la décision en vigueur (et non un renouvellement
  planifié, rejeté ou abandonné, vide).
- Rappel quotidien : le n° cité est celui de la décision qui expire.
- Le lien « Classeur … · page » de la fiche AMM : étiquette du constat à la bonne taille.

## [1.0.7] — 2026-10-22

### Ajouté
- **Corriger un renouvellement** (onglet Renouvellements, crayon) : n° d'AMM, dates de dépôt, de
  décision, de début et de fin (calculée automatiquement ou saisie). Les renouvellements sont
  renumérotés par date et l'échéance, le statut et l'état du dossier de l'AMM sont recalculés ;
  l'ancienne valeur reste dans l'historique.
- **Corriger le classement d'un scan** (onglet Documents, crayon) : période (AMM d'origine ou
  renouvellement), type, date et titre, sans retéléverser le fichier.

### Modifié
- Le siège (Réglementaire siège) peut retirer un scan, comme le CEO : il est archivé et reste dans
  l'historique.
- Une décision ancienne saisie après coup reprend sa place dans l'ordre des dates.

### Corrigé
- Les classeurs et la fiche AMM ne se rafraîchissaient pas après une modification de l'AMM, d'un
  renouvellement ou d'un scan.

## [1.0.6] — 2026-10-20

### Ajouté
- **Menu latéral réductible** : le bouton en bas du menu (‹ / ›) le réduit aux icônes pour laisser la
  place au contenu (classeurs, tableaux) ; le nom de chaque entrée s'affiche en info-bulle. Le choix est
  retenu dans le navigateur.

### Sécurité
- Interface : `follow-redirects` 1.16.1 (dépendance d'axios), failles GHSA-q3jh-wrc6-jgq8 et
  GHSA-8r9p-f939-6h3c publiées le 20/10 et signalées par `npm audit` en CI.

## [1.0.5] — 2026-10-20

### Ajouté
- **Classeurs : pile des décisions et chronologie de l'AMM** (`docs/classeurs-archivage.md`). Toutes
  les décisions scannées, de l'origine au dernier renouvellement, sont agrafées en pile sur la page,
  la plus récente au-dessus. Un clic ouvre la chronologie, de la dernière décision à l'AMM d'origine :
  pièces de chaque période et manques (décision non scannée, date ou n° inconnus, interruption de
  validité, récépissé absent), avec le moyen de les régler (importer le scan depuis la fenêtre).

## [1.0.4] — 2026-10-19

### Corrigé
- **Import des scans classés** : une date plus exacte du classement (décision du 06/04 au lieu du
  16/04 dans le Dashboard) s'applique désormais, même si elle avance un peu l'échéance. Seul un
  recul de plus de six mois (une autre décision, par exemple l'AMM de 2009 au lieu du
  renouvellement de 2019) attend une vérification. Un changement de statut de l'AMM causé par le
  classement est signalé en avertissement. Simulation en production du 19/10 : 589
  avertissements, la plupart des corrections de quelques jours écartées à tort.
- Page d'un import : le placement d'une pièce s'affiche en clair (au lieu de « [object Object] »).

## [1.0.3] — 2026-10-19

### Ajouté
- **Import des scans classés (classement AMM GHPL)** : troisième étape, après le Dashboard et le
  registre. Le manifeste « manifeste_scans_amm_gh.csv » s'importe dans Imports Excel (simulation
  comprise) ; chaque pièce principale est rapprochée de son AMM et de sa période :
  - AMM et produit créés s'ils manquent ; renouvellements obtenus manquants créés ; un dossier
    déposé sans décision est conclu par la décision classée qui le suit ;
  - le classement fait foi pour les dates sûres (date du dossier « RENOUVELLEMENT n - AAAA-MM-JJ »,
    date d'origine « haute » ou « lecture visuelle » de l'année du dossier d'origine) ; une
    correction qui avancerait l'échéance de l'AMM n'est pas appliquée et devient un
    avertissement ; les n° du classement ne font que compléter un n° absent ;
  - récépissés rangés avec le renouvellement qu'ils ont précédé (date de dépôt complétée),
    variations sur la période en vigueur ;
  - renouvellements renumérotés dans l'ordre des dates (une décision ancienne ajoutée après coup
    ne devient pas « la dernière »).
- `scripts/importer_scans_classement.py` (Mac, Python standard) : envoie ensuite chaque fichier à
  sa place, vérifie son SHA-256, reprend là où il s'est arrêté, réessaie quand Render se réveille,
  et écrit un rapport CSV.

### Sécurité
- CI : la faille CVE-2026-106454 de Twisted (serveur IMAP `twisted.mail`, non utilisé par AMM GH)
  est ignorée par `pip-audit` tant qu'aucune version corrigée n'existe.

## [1.0.2] — 2026-10-04

### Corrigé
- **Connexion pendant le démarrage du service** : après une période sans visite, l'API est en
  veille et la première connexion échouait (« Serveur injoignable »). La demande est maintenant
  retentée d'elle-même pendant deux minutes au plus, avec le message « Connexion au service en
  cours ». La page de connexion réveille aussi le service dès son affichage. Si le service ne
  revient pas : « Le service est momentanément indisponible. Veuillez réessayer dans quelques
  instants. » Un refus (identifiants incorrects) n'est pas retenté.

### Sécurité
- CI : audit des dépendances à chaque pull request (`pip-audit` pour Python, `npm audit` pour les
  dépendances livrées de l'interface). Étape 4 du cycle de publication (`docs/versionnement.md`).

## [1.0.1] — 2026-10-04

Première version numérotée selon `docs/versionnement.md`. Elle regroupe tout ce qui a été mis en
ligne depuis la 1.0.0 (47 PR), désormais affiché comme « 1.0.1 » dans l'application.

### En bref
- **Classeurs d'archivage** : jumeau à l'écran de chaque classeur papier, constats Conforme /
  Corriger / Absent, ajout de page, import du scan depuis une page, PDF avec les décisions
  officielles (`docs/classeurs-archivage.md`).
- **Dépôts AMM** : dossier de renouvellement suivi du siège au pays (pièces, échantillons, envoi,
  dépôt, commission, décision), avec messages et ZIP du dossier (`docs/depot-amm.md`).
- **Registre GHPL** : import prudent du classement général des scans, avec avancement visible et
  reprise d'un import coupé (`docs/depot-amm.md`, section 1).
- **Import de dossiers** : rangement automatique, récapitulatif, page compacte avec onglets
  À traiter / En cours / Rangés / Tous et recherche (`docs/workflow-amm.md`, section 8).
- **Version affichée** : le numéro vient de `backend/VERSION` ; l'application n'affiche plus « dev ».

### Import de dossiers : on dépose, c'est rangé (`docs/workflow-amm.md`, section 8)
- **Rangement automatique dès que l'AMM (produit + pays) est identifiée**, sans seuil de
  fiabilité : chaque scan va à sa période (origine ou renouvellement n), les renouvellements
  obtenus lus sont créés, les champs vides complétés, statut / échéance / complétude recalculés,
  bilan et notification. Plus de « Garder / Remplacer », de « Valider » ni de % en avant.
- **Points à vérifier plus tard** (`DossierReviewPoint`) : un écart scan ≠ fiche sur une valeur
  renseignée, un renouvellement en conflit, une décision sans période… ne bloquent plus ; la
  fiche est gardée, le scan rangé, le point listé sur la fiche AMM (badge dans la liste) et sur
  le lot, avec « Appliquer la valeur du scan » (audit `DossierChange`) ou « Ignorer ».
- **Une seule question**, seulement si l'AMM n'est pas identifiable : « c'est quelle AMM ? »
  (sélecteur limité au pays et au périmètre, `POST /dossier-imports/{id}/choose-amm`). Création
  d'AMM uniquement par le siège, sur confirmation.
- **« Voir le scan »** : fichier absent du stockage → 410 « Fichier perdu … réimportez ce
  dossier » au lieu d'un 503 ; la copie déjà rangée dans la fiche est montrée si elle existe.

### Workflow des AMM (règles du responsable, `docs/workflow-amm.md`)
- **Trois statuts, plus un pour la donnée manquante** : **Valide** (vert), **À renouveler**
  (orange, dans les six mois précédant la fin, toujours valide), **Expirée** (rouge, dès le
  lendemain de la date de fin) et **Échéance inconnue** (gris, aucune date connue). « En cours
  d'instruction » disparaît des statuts d'AMM : un dépôt en cours n'empêche plus l'expiration ;
  l'avancement d'un renouvellement (Planifié / Déposé / En instruction) reste porté par le
  renouvellement. Un renouvellement ne compte qu'une fois **obtenu**.
- **Deux dates au lieu d'une** : « Dépôt idéal » (fin − 6 mois, objectif interne) et
  « Limite agence » (fin − 3 mois), affichées dans la fiche, les listes, le tableau de bord,
  l'export et les notifications. Le délai de dépôt par pays (`filing_lead_months`) disparaît.
- **Rappel quotidien** de chaque AMM « À renouveler » aux réglementaires du siège et du pays :
  notification dans l'application et e-mail (`RENEWAL_REMINDER_CHANNELS`), au plus un par AMM,
  destinataire et jour ; il s'arrête dès qu'un renouvellement obtenu repousse l'échéance ou que
  l'AMM expire. Les règles d'alerte existantes (J-365 … DOSSIER, DECISION) sont conservées.
- **Fiche AMM** : frise « Origine → renouvellements obtenus » avec le **document actuel** mis en
  évidence, état du dossier affiché séparément du statut (complet dès que le scan de la décision
  actuelle est rattaché, quelle que soit la validité).
- Migration : toutes les AMM sont recalculées ; les vues `analytics` suivent (`to_renew`,
  `ideal_filing_date`, `agency_filing_deadline`).

### Surveillance
- **Sentry**, actif seulement si `SENTRY_DSN` (web, worker) ou `VITE_SENTRY_DSN` (interface) est
  défini : erreurs et journaux ERROR remontés avec le `request_id` des journaux JSON, la version
  déployée et l'environnement. Aucune donnée personnelle (ni IP, ni cookies, ni corps de requête ;
  identifiant interne de l'utilisateur seulement), traces de performance désactivées par défaut.
  Paquet absent ou DSN vide : l'application démarre comme avant.

### Résilience (campagne de chaos du 18/09/2026, `docs/audit-resilience/RAPPORT.md`)
- **Redis devient optionnel.** Le temps réel part après le commit, borné à 1 s, derrière un
  disjoncteur ; sans Redis on se connecte toujours (repli local du throttle) et les écritures ne
  l'attendent plus. Mesuré : Redis figé sous 40 utilisateurs faisait échouer les lectures et durer
  les écritures 25 s.
- **Délais bornés** sur PostgreSQL (`connect_timeout`, `statement_timeout`, `lock_timeout`,
  `idle_in_transaction_session_timeout`), Redis, S3 et Gmail, réglables par variables
  d'environnement (`.env.example`). Erreur de base ou pool saturé : 503 JSON avec `Retry-After`.
- **Aucune tâche perdue.** Acquittement tardif des tâches Celery ; `recover_pending_work` (toutes
  les 5 min) republie e-mails non partis, aperçus manquants, analyses en attente, et libère les
  analyses interrompues ; e-mails relancés sur ~15 min puis jusqu'à ~5 h, tentatives et dernière
  erreur tracées (`send_attempts`, `last_error`), `Message-ID` stable.
- **Écritures protégées.** `PATCH` d'AMM et de renouvellement atomiques et verrouillés (plus de
  mise à jour perdue ni de modification sans historique) ; une seule version courante par scan ;
  la même décision envoyée deux fois n'en crée qu'une (`200` au second envoi).
- **Exploitation.** uvicorn aussi en un seul processus (arrêt gracieux, `GRACEFUL_TIMEOUT`) ;
  `/api/v1/health/live` ; journaux JSON avec `X-Request-ID` propagé aux tâches ; compteurs
  `amm_degraded_operations_total` ; vue `analytics.v_ops_backlog` pour les alertes Grafana ;
  `manage.py check_integrity` (12 invariants), lancé chaque nuit.
- nginx résout `backend` et `grafana` dynamiquement : il démarre sans Grafana et suit une
  nouvelle IP du backend. Archive ZIP envoyée en flux, bloc par bloc, y compris sous ASGI, et scans lus depuis S3
  sans téléchargement parallèle en mémoire. Reconnexion
  WebSocket avec jitter ; un événement d'AMM ne part plus qu'au groupe de son pays.
- Laboratoire de chaos rejouable : `chaos/` (Compose jetable, toxiproxy, scénarios avant/après).
  Statuts recalculés pour le jour du rejeu après chaque remise à zéro, un seul scénario à la
  fois, `--build` sans risque pour l'image d'origine, état de référence créé par
  `scenarios.py --save-baseline`.

### Ajouté
- **Version de l'API visible.** `/api/v1/health` expose `version` (variable `APP_VERSION` ;
  « dev » si elle est absente ou non conforme : lettres, chiffres et `. _ + -`, 64 caractères au
  plus) et la barre du haut affiche « API en ligne · <version> », « API dégradée » en rouge quand
  la base ne répond plus, « API injoignable » quand l'API ne répond pas. Sonde toutes les 60 s,
  délai de 5 s, sans nouvelle tentative. Le contrôle Redis du health est borné à 1,5 s au total,
  résolution DNS comprise, et les sondes simultanées partagent un même contrôle : un Redis arrêté
  ne ralentit plus la réponse de 4 s. Contrat 200/503 des sondes Railway et Docker inchangé.
- **Le frontend est publié par la CI** (job `netlify`), sur un push vers `main` et seulement
  après le vert du backend et du frontend. Il publie l'état commité : `netlify deploy --build`
  lancé depuis un poste construit le dossier de travail et peut mettre en ligne des
  modifications non commitées — c'est arrivé le 10 septembre. `make deploy-frontend` reste
  disponible en dépannage mais refuse un dépôt non propre. Secrets requis :
  `NETLIFY_AUTH_TOKEN` et `NETLIFY_SITE_ID` ; à défaut le job avertit et passe son tour.
- CI : `makemigrations --check --dry-run` échoue si un modèle a changé sans migration, ou si une
  migration écrite à la main ne correspond pas à l'état des modèles.
- **Retour en arrière sur un renouvellement.** Le plus récent s'annule d'un geste (`DELETE
  /api/v1/renewals/{id}`, bouton sur sa carte) : l'AMM est aussitôt recalculée d'après le
  renouvellement précédent ou son AMM d'origine — elle peut redevenir expirée. Les scans
  rattachés à la décision annulée sont archivés, jamais reportés sur l'AMM d'origine. Seul le
  dernier est annulable : revenir en arrière n'est pas trouer l'historique, que `simple-history`
  conserve avec le détail de ce qui a disparu.

### Modifié
- Création d'AMM : quand la recherche de produit ne donne rien, un réglementaire pays lit
  désormais que le catalogue est tenu par le siège, au lieu de rester devant une liste vide. Les
  permissions sont inchangées — les pays créent AMM, renouvellements et documents dans leur
  périmètre, le catalogue et l'administration restent au siège.
- **Ajouter un renouvellement se fait en une étape.** Un numéro et une date de début suffisent :
  le statut se déduit de la saisie (une date, c'est une décision en main), l'échéance vient de la
  durée de validité du pays et l'AMM est recalculée — une AMM expirée redevient valide d'elle-même.
  Les réglementaires pays comme le siège y ont accès, chacun dans son périmètre. Si un
  renouvellement est déjà ouvert, la décision le conclut au lieu d'être refusée : même dossier,
  même n° d'ordre, date de dépôt conservée. Le workflow (Planifié → Déposé → En instruction)
  reste disponible pour suivre un dépôt en cours, en action secondaire.
- **L'état du dossier n'est plus déclaré, il est constaté.** Il vaut « complet » quand la décision
  qui fait foi — le dernier renouvellement obtenu, sinon l'AMM d'origine — porte son scan, et
  « incomplet » sinon. Le champ devient donc calculé : lecture seule dans l'API et dans l'admin,
  recalculé à chaque ajout, remplacement ou archivage de scan. « Inconnu » disparaît, et la
  colonne « dossier » du classeur Excel n'est plus appliquée à l'import.

### Mise en production (7 septembre 2026)
- Frontend sur Netlify (https://amm-innov.netlify.app), API, worker, PostgreSQL et Redis sur
  Railway ; scans PDF et classeurs d'import sur un bucket Railway (S3, région `ams`,
  `S3_ADDRESSING_STYLE=virtual`).
- Données : 15 pays, 3 gammes, 601 produits, 1 548 AMM, 500 renouvellements, importés du classeur
  (3 lignes en erreur, 104 avertissements, aucun écart de statut avec l'Excel) ; 833 alertes
  historiques créées sans notification (`evaluate_alerts --quiet`).
- La clé de rapprochement des produits a fait son effet : zéro doublon à l'import, contre
  185 groupes sur l'import local antérieur au correctif.

### Ajouté
- Déploiement Netlify + Railway : `netlify.toml`, `railway.json`, guide `docs/deploiement-netlify-railway.md`.
- Revue complète du 5 septembre 2026 (`docs/rapport-revue-2026-09-05.md`) : tests de charge à 30, 60 et
  100 utilisateurs, tests de concurrence, durcissement (voir « Corrigé » et « Sécurité »).
- Pool de connexions PostgreSQL (psycopg, `DB_POOL_MAX_SIZE`) : sans lui, l'API saturait PostgreSQL
  (« too many clients ») dès 30 utilisateurs simultanés sous ASGI.
- `/metrics` protégé par `METRICS_TOKEN` (optionnel) ; `NUM_PROXIES` pour lire la vraie IP cliente.

- Contrat API ↔ frontend outillé : `backend/schema.yaml` (OpenAPI) et `frontend/src/api/schema.d.ts`
  générés et vérifiés en CI (`make api-check`) ; `src/api/contract.ts` fait échouer `tsc` dès qu'une
  réponse de l'API n'est plus assignable aux types du frontend. Quatre dérives corrigées au passage :
  `last_renewal` (colonnes et fiche AMM vides), `amm_id` des renouvellements (redirection
  `/renewals/{id}` cassée), `sent_at` nullable, `range` produit nullable.
- Sélecteur de produit du dialogue « Nouvelle AMM » en recherche serveur (20 résultats) au lieu du
  chargement des 856 produits.
- Jeton WebSocket transmis dans le sous-protocole `amm.jwt` au lieu de l'URL.
- Session de 12 heures glissantes (PRD US1.1) : `REFRESH_TOKEN_LIFETIME` passe de 7 jours à 12 h.
- Plusieurs processus web : `WEB_CONCURRENCY` (1 = Daphne, N = uvicorn avec N workers). Mesuré :
  3 workers font passer le débit de 80 à 167 req/s, 0 erreur à 100 utilisateurs, latence divisée par 2 à 3.
- Cache Django sur Redis : throttles de connexion partagés entre les processus web.
- Photos JPEG/PNG converties sans perte en PDF à l'envoi (`img2pdf`) ; image illisible refusée.
- `/api/docs` et `/api/schema` réservés aux utilisateurs connectés (session admin ou JWT).
- Double création simultanée d'une AMM (même produit × pays) : 400 explicite au lieu de 500.
- Import à blanc (PRD US7.1) : case « Simulation » à l'envoi du classeur, `import_excel --dry-run` ;
  rapport complet (lignes, compteurs, anomalies) sans aucune écriture.
- Doublons de produits : clé de rapprochement `Product.key` (lettres et chiffres), l'import
  retrouve un produit connu malgré une ponctuation différente ; `GET /products/duplicates`,
  `POST /products/merge-duplicates` (CEO, fusionne les groupes sans AMM dans un même pays),
  commande `product_duplicates [--merge]`, écran « Doublons probables » dans la liste des produits.
- Fusion de produits depuis la fiche produit : le frontend envoyait `target_id` là où l'API attend
  `duplicate_id` (bouton inopérant) ; contrat étendu aux corps de requête.

- Répétition du premier déploiement (settings de production, base vide, S3 MinIO, 2 workers
  uvicorn, worker Celery) : quatre blocages corrigés. Le WebSocket refusait l'origine du frontend
  quand il n'est pas servi par l'API (Netlify face à Railway) : les origines CORS sont désormais
  acceptées ; le worker Celery pouvait démarrer avant les migrations du service web (il les
  attend) ; `.dockerignore` (le contexte de build envoyait 550 Mo de `node_modules`) ; sommes de
  contrôle boto3 désactivées sauf exigence (compatibilité Cloudflare R2) et adressage `path`.
  configuration Railway : un seul processus web sur le plan starter (512 Mo), cookie de session
  `SameSite=None` tant que Netlify et l'API restent sur deux domaines.

### Ajouté
- Envoi des e-mails par l'**API Gmail** en HTTPS (`EMAIL_URL=gmail://`, OAuth2 `gmail.send`,
  `scripts/gmail_oauth.py` pour le jeton) : Railway bloque tous les ports SMTP sortants, mesuré
  depuis un conteneur (25, 465, 587, 2525 injoignables ; 443 ouvert).

### Corrigé
- `EMAIL_URL` : le schéma `smtp+tls://`, documenté partout, n'activait pas STARTTLS (le chiffrement
  ne s'obtenait qu'avec `?tls=1`) ; toute configuration SMTP sur le port 587, Gmail compris, aurait
  échoué. Le schéma pilote désormais le chiffrement, le port par défaut suit (587 ou 465), et un
  délai maximal de 15 s évite qu'un serveur muet ne bloque le worker.

### Sécurité
- Dépendances : Django 5.1 (fin de support sécurité) remplacé par Django 5.2 LTS (5.2.17, corrige
  7 CVE 2026), Django REST framework 3.17.2 (2 CVE), pip de l'image mis à jour ; `pip-audit` et
  `npm audit` à zéro.
- Refresh token retiré du `localStorage` : cookie `httpOnly` limité à `/api/v1/auth`, SameSite=Lax,
  rotation à chaque rafraîchissement, contrôle de l'en-tête `Origin` sur refresh et logout.
  Un domaine commun frontend/API est requis en production (guide de déploiement, § 1 bis).
- Couverture pays d'un produit : un réglementaire pays ne voit plus le statut des autres pays.
- Assignation d'une alerte limitée aux utilisateurs ayant accès au pays de l'alerte.
- Statut d'un renouvellement modifiable uniquement via `/renewals/{id}/transition` (plus de PATCH direct).
- Throttle de connexion par IP (30/min) **et** par compte visé (10/min) ; validateurs de mot de passe
  complétés (similarité avec l'email, mots de passe numériques) ; `defusedxml` pour les classeurs importés.

### Corrigé
- Courses de concurrence : création de deux renouvellements ouverts, transitions simultanées sur un même
  renouvellement, doublons de scan sous envois simultanés (verrous de ligne + contrainte d'unicité
  `(amm, sha256)` tant que le document n'est pas archivé).
- Export Excel/CSV : mêmes périmètre, filtres, recherche et tri que la grille des AMM.
- Concurrence Celery de dev limitée à 2 processus (18 connexions PostgreSQL inutiles auparavant).

### Corrigé
- Stockage S3 des scans : `django-storages[s3]` (boto3) installé, un seul jeu de variables
  `DOCUMENT_STORAGE` + `S3_*` reconnu en dev comme en prod.
- Image frontend nginx : `VITE_API_BASE` vide par défaut (la valeur `/api` produisait des appels `/api/api/v1`).
- Dockerfile backend : le stage par défaut est l'image d'exécution, pas l'image de dev.

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
