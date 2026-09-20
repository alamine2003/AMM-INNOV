import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { Health } from '@/api/types';

export const HEALTH_POLL_MS = 60_000;
export const HEALTH_TIMEOUT_MS = 5_000;

export type ApiHealthState = 'checking' | 'online' | 'degraded' | 'unreachable';

/** Valide un corps de /health et le normalise ; lève une Error si ce n'est pas le contrat. */
export function parseHealth(body: unknown): Health {
  if (!body || typeof body !== 'object') throw new Error('Réponse de santé non conforme');
  const raw = body as Record<string, unknown>;
  if (raw.status !== 'ok' && raw.status !== 'degraded') {
    throw new Error('Réponse de santé non conforme');
  }
  if (typeof raw.database !== 'boolean' || typeof raw.redis !== 'boolean') {
    throw new Error('Réponse de santé non conforme');
  }
  return {
    status: raw.status,
    database: raw.database,
    redis: raw.redis,
    version: typeof raw.version === 'string' ? raw.version : '',
  };
}

/** `unreachable` dès que la DERNIÈRE sonde a échoué, même si des données antérieures existent. */
export function toApiHealthState(query: {
  status: 'pending' | 'error' | 'success';
  data?: Health;
}): ApiHealthState {
  if (query.status === 'pending') return 'checking';
  if (query.status === 'error') return 'unreachable';
  return query.data?.status === 'degraded' ? 'degraded' : 'online';
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: async ({ signal }) => {
      const res = await api.get<unknown>('/health', {
        signal,
        timeout: HEALTH_TIMEOUT_MS,
        // 503 fait partie du contrat : son corps dit « degraded ». Tout autre code = injoignable.
        validateStatus: (code) => code === 200 || code === 503,
      });
      return parseHealth(res.data);
    },
    refetchInterval: HEALTH_POLL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: HEALTH_POLL_MS / 2,
    retry: false,
    networkMode: 'always', // hors ligne, la sonde échoue au lieu de rester en pause sur un « en ligne » périmé
  });
}
