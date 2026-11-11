/**
 * Après un déploiement, un onglet resté ouvert garde l'ancienne version : quand il ouvre une
 * page, il demande un fichier (`assets/AlertsPage-<ancien>.js`) qui n'existe plus. Cloudflare
 * répond alors par la page d'accueil HTML, et le navigateur refuse ce « script » (erreur vue le
 * 11/11/2026 après la 1.2.3). La bonne réponse est de recharger : la nouvelle version arrive.
 *
 * Un seul rechargement par minute : si le fichier manque vraiment, on affiche l'erreur au lieu
 * de recharger en boucle.
 */

const KEY = 'amm-gh:stale-chunk-reload';
const WINDOW_MS = 60_000;

const PATTERNS = [
  /failed to fetch dynamically imported module/i, // Chrome
  /error loading dynamically imported module/i, // Firefox
  /importing a module script failed/i, // Safari
  /is not a valid javascript mime type/i, // Safari, fichier remplacé par la page HTML
  /unable to preload css/i, // Vite
  /loading (css )?chunk .* failed/i,
];

/** L'erreur vient-elle d'un fichier de l'ancienne version, disparu depuis le déploiement ? */
export function isStaleChunkError(error: unknown): boolean {
  const message =
    error instanceof Error ? error.message : typeof error === 'string' ? error : String(error ?? '');
  return PATTERNS.some((pattern) => pattern.test(message));
}

/** Recharge la page (une fois par minute au plus). Retourne true si le rechargement part. */
export function reloadForNewVersion(now = Date.now()): boolean {
  try {
    const last = Number(window.sessionStorage.getItem(KEY) ?? 0);
    if (now - last < WINDOW_MS) return false;
    window.sessionStorage.setItem(KEY, String(now));
  } catch {
    // stockage indisponible (navigation privée stricte) : on recharge quand même, une fois
  }
  window.location.reload();
  return true;
}

/** Vite signale l'échec d'un import différé par l'événement `vite:preloadError`. */
export function installStaleChunkReload(): void {
  window.addEventListener('vite:preloadError', (event) => {
    if (reloadForNewVersion()) event.preventDefault();
  });
}
