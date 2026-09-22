# Workflow d'une AMM : origine, renouvellements, statuts et rappels

Ce document décrit, en français simple, les règles métier fixées par le responsable et leur
traduction dans le code. Il fait foi pour le calcul du statut, des dates de dépôt, de l'état du
dossier et du rappel quotidien.

## 1. Origine et renouvellements

Chaque AMM commence par une **origine** (la première décision, avec sa date de début et sa date
de fin). Elle peut ensuite recevoir zéro, un ou plusieurs **renouvellements** successifs,
rattachés à la même AMM.

Un renouvellement n'est pris en compte **que lorsqu'il est OBTENU** (et qu'il porte une date de
fin). Tant qu'il est planifié, en préparation, déposé ou en instruction, il décrit l'avancement
du dossier de renouvellement : il ne change ni la date de fin, ni le statut de l'AMM.

## 2. Document actuel et date de fin

- **Document actuel** = la décision d'origine s'il n'y a aucun renouvellement obtenu, sinon le
  **dernier renouvellement obtenu**.
- La **date de fin de l'AMM actuelle** (`effective_end_date`) est la date de fin de ce document.
  Tout le suivi des échéances repose sur elle.

## 3. Statuts

| Statut | Quand | Couleur |
| --- | --- | --- |
| **Valide** (`VALIDE`) | la date de fin est à plus de six mois | vert |
| **À renouveler** (`A_RENOUVELER`) | on est dans les six mois précédant la fin (jour J compris) ; l'AMM reste valide | orange |
| **Expirée** (`EXPIRE`) | aujourd'hui est après la date de fin | rouge |
| **Échéance inconnue** (`INDETERMINE`) | aucune date de fin connue — donnée manquante, pas une situation métier | gris |

Précisions :

- le jour de la date de fin, l'AMM est encore valide (« À renouveler ») ; le lendemain, elle est
  **Expirée**, automatiquement ;
- une AMM expirée n'est jamais « À renouveler » ;
- **un dépôt en cours n'empêche pas l'expiration** : l'ancien statut « En cours d'instruction »
  n'existe plus. L'avancement d'un renouvellement (Planifié / Déposé / En instruction) reste
  visible sur le renouvellement lui-même, jamais comme statut de l'AMM.

## 4. Dates de dépôt et rappel quotidien

À partir de la date de fin :

- **Dépôt idéal** (`ideal_filing_date`) = fin − 6 mois : objectif interne ;
- **Limite agence** (`agency_filing_deadline`) = fin − 3 mois : date limite de l'autorité.

Dès que l'AMM est « À renouveler », un **rappel quotidien** part vers les réglementaires
concernés (siège et réglementaires du pays de l'AMM) : notification dans l'application, et
e-mail si le canal est activé (`RENEWAL_REMINDER_CHANNELS`, par défaut `IN_APP,EMAIL`). Le texte
nomme le produit, le pays, « expire le … », « Dépôt idéal : … » (ou « dépassé ») et
« Limite agence : … » (ou « dépassée »).

Le rappel est **idempotent** : au plus un par AMM, par destinataire, par canal et par jour
(contrainte unique en base). Il s'arrête tout seul quand l'AMM n'est plus « À renouveler » :
soit un renouvellement obtenu repousse la date de fin, soit l'AMM expire.

Tâche : `apps.notifications.tasks.send_renewal_reminders`, planifiée chaque jour à 07:30
(Celery beat, `CELERY_BEAT_SCHEDULE`), après le recalcul nocturne des statuts (00:05).

Les **règles d'alerte** existantes (J-365, J-180, J-90, J-30, J0, DOSSIER, DECISION) sont
conservées telles quelles et restent désactivables dans « Règles d'alerte ».

## 5. Urgence (indicateur de tri)

L'urgence sert aux listes de priorités et aux tableaux de bord ; elle suit les mêmes dates :

- `EXPIRE` : AMM expirée ;
- `CRITIQUE` : limite agence atteinte ou dépassée ;
- `DEPOT_URGENT` : dépôt idéal atteint ou dépassé (donc « À renouveler ») ;
- `A_PLANIFIER` : échéance dans un an ou moins, ou échéance inconnue ;
- `OK` : le reste.

Un dépôt en cours ne masque plus l'urgence (l'ancien niveau « En instruction » a disparu).

## 6. État du dossier

Le dossier est **complet** quand le **scan de la décision actuelle** (origine ou dernier
renouvellement obtenu) est rattaché à l'AMM, **incomplet** sinon. Il est totalement indépendant
de la validité : une AMM expirée dont la décision est scannée reste « Dossier complet ».

## 7. Qui saisit quoi

Les réglementaires téléversent les décisions et enregistrent les renouvellements. Tout le reste
— statut, urgence, dates de dépôt, état du dossier, alertes, rappels — est calculé.

## 8. Où c'est écrit dans le code

| Quoi | Où |
| --- | --- |
| Calcul du statut, des dates et de l'état du dossier | `backend/apps/amm/services/status.py` |
| Champs stockés (`status`, `urgency`, `effective_end_date`, `ideal_filing_date`, `agency_filing_deadline`, `dossier_state`) | `backend/apps/amm/models.py` |
| Recalcul nocturne | `apps.amm.tasks.recompute_all_statuses` |
| Rappel quotidien « À renouveler » | `backend/apps/notifications/reminders.py` |
| Règles d'alerte | `backend/apps/alerts/` |
| Projection « Après validation » de l'import de dossier | `backend/apps/imports/dossier/projection.py` |
| Miroir côté interface (libellés, couleurs, `statusFor`, `filingDates`) | `frontend/src/lib/urgency.ts` |

## 9. Algorithme, en une page

```
renouvellements_obtenus = renouvellements où statut = OBTENU et date de fin renseignée
document_actuel        = le plus récent des renouvellements obtenus, sinon l'origine
fin                    = date de fin du document actuel

si fin est inconnue        -> INDETERMINE (« Échéance inconnue »)
sinon si aujourd'hui > fin -> EXPIRE
sinon si aujourd'hui >= fin − 6 mois -> A_RENOUVELER
sinon                      -> VALIDE

dépôt idéal   = fin − 6 mois
limite agence = fin − 3 mois

dossier = COMPLET si le scan (kind=AMM, courant) du document actuel est rattaché, sinon INCOMPLET
```
