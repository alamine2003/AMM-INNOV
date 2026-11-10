# Palier 1.2.0 : validation, déploiement, retour arrière

La 1.2.0 termine la remise en ordre de l'architecture commencée en 1.1.8 (revue d'architecture
du 09/11/2026). Le contenu est dans `CHANGELOG.md`. Ce document répond aux exigences d'un palier
(`docs/versionnement.md`).

## Ce qui change pour les utilisateurs

Rien de visible, hors un cas. Les boutons réservés au siège et au CEO dans les classeurs
s'affichent désormais d'après les droits renvoyés par le serveur, et non plus d'après une liste
de rôles recopiée dans l'interface. Ils restent montrés aux mêmes personnes.

Pas de migration de base de données. Un seul ajout dans l'API : le champ `actions` de `/me` et
de la réponse de connexion.

## Validation (10/11/2026)

| Contrôle | Résultat |
| --- | --- |
| Tests backend (Postgres 16, Redis, Python 3.12, versions figées) | 673 réussis, couverture 91 % |
| Tests frontend (Vitest) | 155 réussis ; lint, typecheck, build OK |
| Règles d'import des couches (`test_architecture.py`) | aucune exception |
| Migrations | aucune (`makemigrations --check`) |
| Schéma OpenAPI | seul ajout : `actions` de `/me` ; types frontend régénérés |
| `pip-audit` sur `requirements.txt` | aucune vulnérabilité, aucune exception |
| `npm audit --omit=dev` (code livré) | aucune vulnérabilité |
| `npm audit` (outils de développement) | 10 alertes, dont 2 critiques dans Vitest 3 (`tinypool`, `@vitest/mocker`) |
| `check_integrity` | 11 contrôles, mêmes invariants qu'en 1.1.9 |

Les alertes de `npm audit` concernent seulement l'outil de test, jamais déployé. La correction
demande Vitest 5, une version majeure : Dependabot l'exclut par politique. C'est à traiter dans
une mise à jour corrective dédiée (1.2.1).

## Déploiement

1. Fusionner la PR `version-1.2.0`. La CI de `main` doit être verte.
2. Render redéploie l'API tout seul. Contrôle : `/api/v1/health` répond `"version":"1.2.0"`.
3. Cloudflare Pages reconstruit le frontend. S'il ne le fait pas (cas du 08/11), pousser un
   commit sur `main` ou créer un deploy hook.
4. Recharger AMM GH. Avec un compte siège, ouvrir un classeur : les boutons « Titre » et
   « Supprimer la page » sont là. Avec un compte pays, ils n'y sont pas.
5. Poser le tag `v1.2.0` sur le merge.

## Retour arrière

La 1.2.0 n'a ni migration ni changement de données : revenir à la 1.1.9 est sans risque.

- **API** : dans Render, service `amm-innov-api`, onglet *Events*, « Rollback » sur le
  déploiement de la 1.1.9 (cb9abb9).
- **Interface** : dans Cloudflare Pages, projet `amm-gh`, *Deployments*, « Rollback to this
  deployment » sur celui de cb9abb9.
- **Code** : `git revert` du merge de la 1.2.0 sur une branche `version-1.2.1`, puis PR.

Une interface 1.2.0 avec une API 1.1.9 fonctionne aussi, sans les boutons réservés : `actions`
manque, et `useCan` répond « non ». C'est le sens sûr.
