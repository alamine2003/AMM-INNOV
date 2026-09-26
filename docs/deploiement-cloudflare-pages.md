# Interface AMM GH sur Cloudflare Pages

Depuis le 26/09/2026, l'interface (React/Vite) est publiée sur **Cloudflare Pages** : gratuit,
bande passante illimitée, 500 publications par mois, sans système de crédits. Netlify
(`amm-innov.netlify.app`) est gardé en secours ; l'API reste sur Render.

## 1. Créer le projet (une seule fois)

Tableau de bord Cloudflare → **Workers & Pages** → **Create** → onglet **Pages** →
**Connect to Git** → autoriser GitHub → dépôt `alamine2003/AMM-INNOV`.

| Réglage | Valeur |
| --- | --- |
| Project name | `amm-gh` (donne `https://amm-gh.pages.dev`) |
| Production branch | `main` |
| Framework preset | `None` |
| Build command | `cd frontend && npm ci && npm run build` |
| Build output directory | `frontend/dist` |
| Root directory | *(vide)* |

Variables d'environnement (Production **et** Preview) :

| Variable | Valeur |
| --- | --- |
| `NODE_VERSION` | `24` |
| `VITE_API_BASE` | `https://amm-innov-api.onrender.com` |
| `VITE_WS_URL` | `wss://amm-innov-api.onrender.com/ws/` |

`VITE_API_BASE` ne se termine pas par `/api` : le client ajoute `/api/v1` lui-même.

Le routage de l'application (`_redirects`) et les en-têtes de sécurité (`_headers`) sont dans
`frontend/public/` : ils sont publiés avec le site, rien à régler dans Cloudflare.

## 2. Autoriser la nouvelle adresse côté API (Render)

Render → service `amm-innov-api` → **Environment** :

| Variable | Valeur |
| --- | --- |
| `CORS_ALLOWED_ORIGINS` | `https://amm-gh.pages.dev,https://amm-innov.netlify.app` |
| `CSRF_TRUSTED_ORIGINS` | `https://amm-gh.pages.dev,https://amm-innov.netlify.app` |
| `FRONTEND_URL` | `https://amm-gh.pages.dev` (liens des e-mails) |

Si Cloudflare a attribué un autre nom (`amm-gh-xxx.pages.dev`), utiliser celui-là partout.
Les WebSockets acceptent automatiquement les origines de `CORS_ALLOWED_ORIGINS`.

## 3. Vérifier

- `https://amm-gh.pages.dev/login` affiche la page de connexion AMM GH ;
- la connexion fonctionne, le badge « API en ligne » et « Live » sont verts ;
- une URL profonde (`/amm`, `/imports/dossiers`) rechargée avec F5 s'ouvre (pas de 404).

Chaque fusion dans `main` republie l'interface ; chaque PR reçoit une adresse d'aperçu.
