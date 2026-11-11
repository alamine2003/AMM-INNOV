/**
 * Réveil de l'API AMM GH (Render gratuit), exécuté par Cloudflare toutes les 5 minutes.
 *
 * Render endort l'API après 15 minutes sans requête ; le réveil prend environ une minute et
 * arrête Celery (imports, rappels, synchronisation GHPL) pendant le sommeil. Les tâches
 * planifiées de GitHub Actions ne partent que quelques fois par jour : celles de Cloudflare
 * (déclencheurs Cron des Workers, offre gratuite) partent à l'heure.
 *
 * Installation (tableau de bord Cloudflare, aucun secret) : voir docs/audit-infrastructure-1.2.4.md.
 * Variable facultative API_URL (défaut ci-dessous).
 */
const DEFAULT_URL = 'https://amm-innov-api.onrender.com/api/v1/health/live';

async function ping(env) {
  const url = (env && env.API_URL) || DEFAULT_URL;
  const started = Date.now();
  try {
    const response = await fetch(url, { headers: { 'User-Agent': 'amm-gh-keepalive' } });
    return { url, status: response.status, ms: Date.now() - started };
  } catch (error) {
    return { url, error: String(error), ms: Date.now() - started };
  }
}

export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(ping(env).then((result) => console.log(JSON.stringify(result))));
  },
  // Appel direct du Worker : simple réponse, sans relayer vers l'API.
  async fetch() {
    return new Response('AMM GH keepalive : planifié toutes les 5 minutes.\n', {
      headers: { 'content-type': 'text/plain; charset=utf-8' },
    });
  },
};
