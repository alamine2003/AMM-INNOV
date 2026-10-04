# Versionnement progressif d'AMM GH

AMM GH avance vers la version 2.0.0 par petits pas. Chaque cycle compte **neuf mises à jour
correctives**, puis un **palier**.

## 1. La suite des versions

| Cycle | Versions | Ensuite |
| --- | --- | --- |
| 1.0 | 1.0.0 (version initiale), 1.0.1 … 1.0.9 | palier 1.1.0 |
| 1.1 | 1.1.1 … 1.1.9 | palier 1.2.0 |
| 1.2 à 1.8 | 1.x.1 … 1.x.9 | palier suivant |
| 1.9 | 1.9.1 … 1.9.9 | version majeure **2.0.0** |

« La version 1.1 » s'écrit `1.1.0` : c'est le numéro du palier lui-même, avant ses neuf correctifs.

Le numéro en cours est dans `backend/VERSION` ; l'historique est dans `CHANGELOG.md`. La 1.0.1
(4 octobre 2026) regroupe tout ce qui a été mis en ligne depuis la 1.0.0 du 5 septembre 2026.

## 2. Ce que contient chaque type de version

**Mise à jour corrective** (`.1` à `.9`) :

- corrections de bugs ;
- mises à jour de sécurité ;
- optimisations de performances ;
- mises à jour de dépendances ;
- améliorations de stabilité ;
- ajustements mineurs de l'infrastructure ;
- améliorations sans rupture majeure.

**Palier** (1.0.9 → 1.1.0, 1.1.9 → 1.2.0…) : une évolution fonctionnelle ou technique plus
importante. Il doit inclure :

- un ensemble cohérent de nouvelles fonctionnalités ;
- les corrections accumulées pendant le cycle précédent ;
- une validation complète de la sécurité ;
- des tests de non-régression ;
- une mise à jour de la documentation ;
- un plan de déploiement et de retour arrière.

**Version majeure 2.0.0** (après 1.9.9). Elle peut comprendre :

- une nouvelle architecture ;
- des changements fonctionnels importants ;
- une modernisation complète de l'infrastructure ;
- une amélioration majeure de la sécurité ;
- une migration des données ou des configurations ;
- des changements incompatibles avec la série 1.x ;
- une nouvelle documentation technique et utilisateur.

## 3. Le cycle de publication, étape par étape

Chaque version suit ces onze étapes. La colonne de droite dit comment l'étape est remplie
aujourd'hui dans AMM GH.

| # | Étape | Dans AMM GH |
| --- | --- | --- |
| 1 | Identification et priorisation des bugs | Liste des points retenus pour la version |
| 2 | Développement des corrections et améliorations | Une branche par sujet |
| 3 | Révision du code | Pull request sur GitHub, relue avant fusion |
| 4 | Contrôles de sécurité | CI : `pip-audit` (dépendances Python) et `npm audit` (dépendances livrées, niveau élevé) ; Dependabot ; relecture des droits et des entrées dans la pull request |
| 5 | Tests automatisés et manuels | CI (pytest, vitest) et essai à la main des écrans touchés |
| 6 | Tests de non-régression | Toute la suite de tests passe, pas seulement les nouveaux |
| 7 | Validation en préproduction | **Pas encore de préproduction** : CI au vert et essai sur une copie locale |
| 8 | Sauvegarde et retour arrière | Voir la section 5 |
| 9 | Déploiement en production | Fusion dans `main` : Render et Cloudflare Pages se mettent à jour |
| 10 | Surveillance après déploiement | `/api/v1/health` affiche le nouveau numéro ; pastille « API en ligne » ; un essai de connexion |
| 11 | Publication du journal des modifications | `CHANGELOG.md`, section de la version |

Étape 4 : si un audit échoue, une vulnérabilité vient d'être publiée sur une dépendance. Mettre
la dépendance à jour dans une version corrective. S'il n'existe pas encore de correctif, l'exception
se note dans la CI (`pip-audit --ignore-vuln <identifiant>`) avec la raison et une date de revue.

L'étape 7 sera remplie par une vraie préproduction quand l'hébergement sera pris en charge par
l'entreprise. D'ici là, on ne coche pas « préproduction » : on note « CI + essai local ».

## 4. Publier une version

Le numéro est écrit à un seul endroit de référence, `backend/VERSION`. L'API le lit et
l'application l'affiche dans la barre du haut. `frontend/package.json` et son fichier de
verrouillage portent le même numéro.

1. Pendant le cycle, noter chaque changement dans `CHANGELOG.md`, sous « Non publié ».
2. Quand la version est prête :

   ```
   python3 scripts/release.py publier
   ```

   Le script calcule le numéro suivant selon le tableau de la section 1, met à jour les trois
   fichiers et date la section du journal. Il refuse de publier si « Non publié » est vide.
3. Ouvrir la pull request, attendre la CI, fusionner.
4. Poser l'étiquette sur la version publiée, une ligne à la fois :

   ```
   git checkout main
   git pull
   cat backend/VERSION
   git tag v1.0.2
   git push origin v1.0.2
   ```

   `cat` doit afficher le numéro publié. Sinon la copie locale n'est pas à jour : ne pas poser
   l'étiquette.

Autres commandes :

- `python3 scripts/release.py` : affiche la version en cours et la suivante ;
- `python3 scripts/release.py --check` : vérifie que les fichiers et le journal sont cohérents.
  La CI lance cette vérification à chaque pull request : un numéro sauté (1.0.1 → 1.0.3), un
  retour en arrière ou un fichier oublié fait échouer la CI.

On ne choisit donc jamais le numéro à la main.

## 5. Sauvegarde et retour arrière

- **Base de données** : le workflow *Base Render* la sauvegarde chaque nuit (artefact gardé
  90 jours). Avant un palier ou une migration de données, lancer l'action `backup` à la main et
  télécharger l'artefact (`docs/deploiement-render.md`, section 3).
- **Application** : dans le tableau de bord Render, *Rollback* sur le déploiement précédent. Sur
  Cloudflare Pages, *Rollback to this deployment* sur la version précédente.
- **Code** : annuler la fusion sur GitHub (*Revert*), ce qui redéploie l'état précédent.
- **Migration de données** : une migration qui supprime ou transforme des données ne se défait
  pas par un simple retour de code. Elle exige une sauvegarde prise juste avant, et la procédure
  de restauration doit être écrite dans la pull request.

## 6. Limites connues

- Neuf correctifs par cycle est une règle fixe. Une nouvelle fonctionnalité importante attend
  donc le palier ; un dixième correctif urgent en fin de cycle oblige à publier le palier.
- Les versions antérieures à la 1.0.1 n'ont pas suivi ce cycle : 47 pull requests ont été mises
  en ligne entre la 1.0.0 et la 1.0.1 sans numéro.
