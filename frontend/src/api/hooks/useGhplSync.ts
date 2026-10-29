import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { GhplCopyMergeResult, GhplSyncedFile, GhplSyncStatus, Paginated } from '@/api/types';

/** État de la synchronisation AMM GHPL ; relu toutes les 5 s pendant un passage. */
export function useGhplSync() {
  return useQuery({
    queryKey: queryKeys.ghplSync.status(),
    queryFn: async () => (await api.get<GhplSyncStatus>('/ghpl-sync')).data,
    refetchInterval: (query) => (query.state.data?.running ? 5000 : 60_000),
  });
}

export function useGhplSyncFiles(state: string, page = 1, enabled = true) {
  return useQuery({
    queryKey: queryKeys.ghplSync.files(state, page),
    queryFn: async () =>
      (
        await api.get<Paginated<GhplSyncedFile>>('/ghpl-sync/files', {
          params: { state, page, page_size: 20 },
        })
      ).data,
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useRunGhplSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post('/ghpl-sync/run')).data,
    onSuccess: () => {
      // Le passage démarre dans le worker : on relit l'état aussitôt, puis toutes les 5 s.
      setTimeout(() => void qc.invalidateQueries({ queryKey: queryKeys.ghplSync.all }), 1500);
      void qc.invalidateQueries({ queryKey: queryKeys.imports.all });
    },
  });
}

/** Fusionne des fiches en double (simples copies) dans la fiche du pays. */
export function useMergeGhplCopies() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (pairs: { copy: string; keep: string }[]) =>
      (await api.post<GhplCopyMergeResult>('/ghpl-sync/merge-copies', { pairs })).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.ghplSync.all });
      void qc.invalidateQueries({ queryKey: queryKeys.amms.all });
    },
  });
}
