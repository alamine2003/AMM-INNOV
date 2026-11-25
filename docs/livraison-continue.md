# Livraison continue d'AMM GH (1.3.9)

De la fusion à la production, sans commande sur le serveur : on pose l'étiquette, GitHub vérifie
et prépare, Mohamed approuve, le serveur installe lui-même et dit si c'est réussi.

```
 fusion dans main ──► CI : tests backend et frontend, images sha-<commit>   (ci.yml, inchangé)
        │
 git tag vX.Y.Z ──► Livraison (livraison.yml)
                     1. Vérifier    étiquette = backend/VERSION = CHANGELOG, commit sur main,
                                    CI verte, images construites, composition lisible
                     2. Images      images testées nommées X.Y.Z, rapport de vulnérabilités,
                                    version publiée sur GitHub (Releases)
                     3. Production  ⏸ approbation de Mohamed
                                    └─► demande d'installation « serveur-stellarix »
                                                    │
 serveur (VPN) ◄── agent livrer.sh, chaque minute ──┘
                     contrôles → sauvegarde vérifiée → checkout vX.Y.Z → TAG=X.Y.Z
                     → pull → up -d → santé de l'API = X.Y.Z ?
                         oui : « en service »          → Livraison au vert
                         non : retour à la version d'avant → Livraison au rouge
```

## Pourquoi le serveur vient chercher le travail

Le serveur Stellarix n'est joignable que par le VPN FortiClient : un robot GitHub ne peut pas s'y
connecter en SSH (c'est ce que faisait l'ancien `deploy.yml`, jamais utilisé, retiré). Ouvrir le
SSH à Internet ou installer un robot GitHub sur le serveur (« self-hosted runner ») ouvrirait une
porte sur une machine qui porte aussi JUSTI GH ; GitHub déconseille ce robot sur un dépôt public.

Le serveur interroge donc GitHub, en sortie seulement, comme il le fait déjà pour `git fetch` et
les images. Son jeton ne sait faire qu'une chose : lire et répondre aux demandes de déploiement de
ce dépôt. Il ne peut ni pousser du code ni lire les secrets.

## Ce que l'agent vérifie avant de toucher à quoi que ce soit

- La demande vient du workflow (`github-actions[bot]`), donc d'une livraison approuvée.
- L'étiquette est de la forme `vX.Y.Z`, elle est sur `main` et pointe sur le commit annoncé.
- Aucun fichier du dépôt n'a été modifié à la main sur le serveur (il serait écrasé).
- Aucune commande d'administration ne tourne (`manage.py relire_congo` …) : l'installation est
  alors reportée et repart seule à la fin de la commande. GitHub affiche « En attente ».
- La sauvegarde chiffrée et vérifiée de la base réussit (`sauvegarder.sh`, la même que la nuit,
  copiée hors de la machine comme elle). Sinon rien n'est installé.

## Le moment du redémarrage

Il redémarre au moment où Mohamed approuve, en général moins d'une minute après (la sauvegarde
vérifiée prend quelques minutes avant). La règle reste la même : approuver hors des heures de
travail, ou quand personne n'utilise l'application. Une demande approuvée n'expire pas avant
45 minutes ; au-delà, elle est abandonnée et il faut relancer.

## Retour en arrière

- **Automatique** : si l'API ne répond pas « ok » avec le bon numéro dans les 3 minutes, l'agent
  remet l'étiquette et les images d'avant. Le code revient ; la base, non : si la nouvelle
  version a déjà transformé la base (migrations), restaurer la sauvegarde faite juste avant
  (`scripts/serveur/restaurer_base.sh`, section 4 de `deploiement-serveur-partage.md`).
- **Volontaire** : Actions > Livraison > Run workflow, étiquette `v1.3.9` par exemple. Même
  chemin : vérification, approbation, sauvegarde, installation.

## Mise en place (une seule fois, après l'installation manuelle de la 1.3.9)

Sur GitHub (compte de Mohamed) :

1. Settings > Environments > `production` (le créer s'il n'existe pas) > **Required reviewers** :
   se mettre soi-même. Décocher « Prevent self-review » : c'est la même personne qui pose
   l'étiquette et qui approuve.
2. Créer le jeton du serveur : Settings (du compte) > Developer settings > Personal access tokens
   > Fine-grained tokens > Generate. Dépôt : `alamine2003/AMM-INNOV` seulement. Permission :
   **Deployments : Read and write**, rien d'autre. Durée : un an (le noter pour le renouveler).

Sur le serveur :

```bash
cd /home/deploy/amm-gh
sudo scripts/serveur/configurer.sh GITHUB_DEPLOY_TOKEN     # collé au clavier, masqué
sudo scripts/serveur/installer_livraison.sh
```

Le jeton va dans `.env.livraison`, lu par l'agent seul : `.env` est lu par les conteneurs, il n'y
est donc jamais.

## Suivre et dépanner

| Où | Quoi |
|---|---|
| GitHub > Actions > Livraison | l'avancement, l'approbation, le résultat du serveur |
| GitHub > Releases | les versions publiées et leurs notes |
| `sudo journalctl -u amm-gh-livraison -f` | ce que fait l'agent, minute par minute |
| `livraisons/journal.log` | l'historique des installations (et la sortie de la sauvegarde) |
| `sudo systemctl status amm-gh-livraison.timer` | le minuteur tourne-t-il ? |
| `sudo scripts/serveur/installer_livraison.sh --retirer` | revenir aux installations à la main |

Les installations à la main (section 5 de `deploiement-serveur-partage.md`) restent possibles :
l'agent ne fait rien tant qu'aucune demande approuvée n'attend.

## Ce qui reste hors de la chaîne

L'interface publiée sur Cloudflare Pages (`amm-gh.pages.dev`) se met encore à jour à chaque
fusion, par l'intégration de Cloudflare, avant l'installation de l'API. La faire passer par
l'étape 3 demande un jeton Cloudflare et l'arrêt de la publication automatique de Pages : prévu
avec le passage au vrai nom de domaine, qui fera servir l'interface par le serveur lui-même.
