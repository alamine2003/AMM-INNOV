import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { AuditAction, AuditFilters, AuditPage } from '@/api/types';

export interface AuditQuery {
  user?: string;
  model?: string;
  action?: AuditAction | '';
  country?: string;
  since?: string;
  until?: string;
}

/** Audit (CEO et siège) : qui a fait quoi, quand, du plus récent au plus ancien. */
export function useAudit(query: AuditQuery, page = 1) {
  const params = Object.fromEntries(Object.entries({ ...query, page }).filter(([, value]) => !!value));
  return useQuery({
    queryKey: ['audit', params],
    queryFn: async () => (await api.get<AuditPage>('/audit', { params })).data,
    placeholderData: keepPreviousData,
  });
}

/** Valeurs des filtres : types suivis, actions, personnes. */
export function useAuditFilters() {
  return useQuery({
    queryKey: ['audit', 'filters'],
    queryFn: async () => (await api.get<AuditFilters>('/audit/filters')).data,
    staleTime: 5 * 60_000,
  });
}
