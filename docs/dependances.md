# Dépendances Python figées

Depuis la 1.2.0, les versions exactes des dépendances du backend sont figées. Avant, la CI et
Render installaient la dernière version permise par une borne basse (`pypdf>=6.19.0`) : le
05/11/2026, pypdf 7.0.0 est sorti et a cassé la CI de la 1.1.7 sans aucun changement de code.

| Fichier | Rôle | Modifié par |
| --- | --- | --- |
| `backend/requirements.in` | ce dont l'application a besoin, avec des bornes | une personne |
| `backend/requirements.txt` | versions exactes de tout ce qui est installé (production) | `pip-compile` |
| `backend/requirements-dev.in` | outils de test et de lint, en plus de la production | une personne |
| `backend/requirements-dev.txt` | versions exactes pour la CI et le développement | `pip-compile` |

La CI, l'image Docker et Render installent `requirements.txt` (ou `requirements-dev.txt`) :
tout le monde a exactement les mêmes versions. `pip-audit` contrôle `requirements.txt` sans
aucune exception.

## Ajouter ou mettre à jour une dépendance

Avec Python 3.12, comme en production :

```
pip install pip-tools
cd backend
# 1. modifier requirements.in (ou requirements-dev.in)
pip-compile --strip-extras --no-emit-index-url --output-file requirements.txt requirements.in
pip-compile --strip-extras --no-emit-index-url --output-file requirements-dev.txt requirements-dev.in
# 2. committer les .in et les .txt ensemble
```

Pour monter une seule dépendance : `pip-compile --upgrade-package pypdf ...` avec les mêmes
options.

Dependabot reconnaît les fichiers produits par `pip-compile` : chaque lundi, il propose une PR
qui met à jour les `.txt` (mises à jour mineures et correctives seulement). La CI teste ces
versions avant la fusion.
