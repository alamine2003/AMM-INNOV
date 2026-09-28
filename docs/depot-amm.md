# Registre GHPL et dépôt des AMM

## 1. Import du registre GHPL (classement général des scans)

Le fichier `0_REGISTRE AMM GHPL.xlsx` du dossier Nextcloud « AMM GHPL - CLASSEMENT GENERAL » croise
le Dashboard AMM Afrique et les scans classés par gamme, pays et produit. Il s'importe au même endroit
que le Dashboard : **Imports Excel**. L'application le reconnaît à ses onglets `_Consolidation` et
`_Docs`.

Le Dashboard reste la référence. L'import du registre est donc prudent :

| Ligne du registre | Ce que fait l'import |
| --- | --- |
| AMM connue, n° ou date d'origine vides dans AMM GH | complète ces champs (jamais d'écrasement), tracé dans l'historique « Complété depuis le registre GHPL » |
| Statut dossier « Déposé » | ouvre un renouvellement **déposé**, daté de la dernière attestation de dépôt classée (`_Docs`), sauf si un dépôt ou une instruction est déjà en cours |
| « Classement seul » (absente du Dashboard) | crée l'AMM avec le n° et la date d'origine lus, notée « Présentation absente du Dashboard AMM Afrique » |
| « Acte classé plus récent que le Dashboard » | avertissement : importer le scan dans « Import de dossiers AMM » |
| AMM du Dashboard introuvable | avertissement : importer d'abord le Dashboard AMM Afrique à jour |
| Pays non suivi (RDC, Mauritanie) | avertissement |
| « PRÉSENTATION NON IDENTIFIÉE » | ignorée : rien n'est créé |

**Produits** : avant de créer un produit, l'import cherche le même produit écrit autrement, d'abord
parmi les produits suivis dans le pays, puis dans tout le catalogue :

- « OMEPRAL 20MG GELULE B28 » = « OMEPRAL 20MG GEL B/28 » ;
- « TENSOPLUS 2,5MG-10MG-10MG CPR B30 » = « TENSOPLUS 10MG/2,5MG/10MG CPR B/30 » ;
- « KETOPROFENE-GH » = « KETOPROFEN GH ».

Il faut la même marque, la même forme, les mêmes dosages et la même boîte quand elle est indiquée.
Quand deux fiches du catalogue sont des doublons (mêmes dosages, même boîte), c'est la plus utilisée
qui est reprise. Sinon le produit est créé, dans la gamme du registre.

**Conseil** : lancer d'abord en **simulation**. La page du lot ouvre sur les avertissements, avec un
filtre par résultat (erreurs, avertissements, créées, mises à jour, ignorées) et un résumé par pays.

L'onglet « Parametres pays » (durées de validité, délais) n'est pas importé : ses valeurs sont des
hypothèses non confirmées.

Les scans du classement (plus de 3 600 documents) s'importeront ensuite par « Import de dossiers
AMM », une fois synchronisés depuis Nextcloud.
