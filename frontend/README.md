# AMM INNOV — Frontend

SPA React 19 + TypeScript (Vite 6) de suivi des AMM en Afrique. Consomme l'API Django `/api/v1` et le WebSocket `/ws/`.

## Démarrage

```bash
npm install
npm run dev          # http://localhost:5173, proxy /api et /ws vers http://localhost:8000
npm run dev:mock     # même chose sans backend : API simulée par MSW dans le navigateur
```

Comptes de démonstration (mode mock, mot de passe `Passw0rd!`) :

| E-mail | Rôle |
|---|---|
| `ceo@amm-innov.test` | CEO / administrateur |
| `siege@amm-innov.test` | Réglementaire siège |
| `senegal@amm-innov.test` | Réglementaire pays (SN) |
| `ci@amm-innov.test` | Réglementaire pays (CI, CM) |

## Scripts

| Commande | Rôle |
|---|---|
| `npm run build` | `tsc -b` puis build Vite dans `dist/` |
| `npm run preview` | Sert le build |
| `npm run lint` | ESLint + vérification Prettier |
| `npm run format` | Prettier en écriture |
| `npm run typecheck` | `tsc -b --noEmit` |
| `npm run test` | Vitest (jsdom + MSW) |

## Configuration

Copier `.env.example` en `.env` si nécessaire : `VITE_API_BASE` (préfixe de l'API, vide = même origine), `VITE_WS_URL` (URL WebSocket, vide = `ws(s)://<host>/ws/`), `VITE_USE_MOCKS=1` pour activer MSW.

## Organisation

```
src/
  app/        routeur, providers, thème, layout (AppBar, Drawer), gardes RequireAuth / RequireRole
  api/        client axios (JWT + refresh), types du contrat, queryKeys, hooks React Query par ressource
  features/   auth, dashboard, amm, renewals, documents, alerts, catalog, admin, imports, notifications
  realtime/   useRealtime (WebSocket, reconnexion 1 s → 30 s, repli polling 60 s), table d'invalidation
  components/ composants partagés (chips, dropzone, dialogues…)
  lib/        dates (JJ/MM/AAAA, date-fns fr), couleurs d'urgence, téléchargement, i18n
  locales/    fr.json (toutes les chaînes passent par t())
  mocks/      handlers MSW + données de démo (3 pays, 10 AMM)
  test/       setup Vitest et utilitaires de rendu
```

## Rôles

- `CEO_ADMIN` : tout, y compris suppression de documents et gestion des comptes siège.
- `HQ_REGULATORY` : tous les pays, référentiels, règles d'alerte, imports, création des réglementaires pays.
- `COUNTRY_REGULATORY` : ses pays uniquement (AMM, renouvellements, documents, alertes).
