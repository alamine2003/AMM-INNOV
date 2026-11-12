/**
 * Erreurs de l'interface envoyées au journal des erreurs d'AMM GH (Administration › Erreurs).
 *
 * Seulement pour un utilisateur connecté, dix par session au plus, la même une seule fois :
 * une page qui boucle sur une erreur ne remplit pas le journal. On envoie le type, le message, la
 * pile et la page ouverte ; jamais ce qui a été saisi. Une erreur d'envoi est ignorée.
 */
import { api } from '@/api/client';
import { useAuthStore } from '@/features/auth/authStore';
import { isStaleChunkError } from '@/lib/staleChunks';

const MAX_PER_SESSION = 10;
const sent = new Set<string>();

export function reportError(error: unknown, path = window.location.pathname): boolean {
  if (!useAuthStore.getState().access) return false;
  if (isStaleChunkError(error)) return false; // nouvelle version : la page se recharge
  const err = error instanceof Error ? error : new Error(String(error ?? 'Erreur inconnue'));
  const key = `${err.name}:${err.message}:${path}`;
  if (sent.has(key) || sent.size >= MAX_PER_SESSION) return false;
  sent.add(key);
  void api
    .post('/client-errors', {
      kind: err.name.slice(0, 120),
      message: (err.message || err.name).slice(0, 500),
      stack: (err.stack ?? '').slice(0, 8000),
      path: path.slice(0, 300),
    })
    .catch(() => undefined);
  return true;
}

/** Erreurs non rattrapées (hors affichage des pages, déjà couvert par RouteError). */
export function installErrorReporting(): void {
  window.addEventListener('error', (event) => reportError(event.error ?? event.message));
  window.addEventListener('unhandledrejection', (event) => {
    const reason: unknown = event.reason;
    // Les refus de l'API (axios) sont déjà affichés à l'utilisateur et tracés côté serveur.
    if (reason && typeof reason === 'object' && 'isAxiosError' in reason) return;
    reportError(reason);
  });
}

/** Pour les tests. */
export function resetReportedErrors(): void {
  sent.clear();
}
