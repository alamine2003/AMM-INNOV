import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { Paginated, TrashEntry } from '@/api/types';

export const trashKeys = {
  list: (state: TrashState) => ['trash', state] as const,
};

export type TrashState = 'deleted' | 'restored' | 'all';

/** Corbeille (CEO et siège) : ce qui a été supprimé, jamais effacé. */
export function useTrash(state: TrashState, page = 1) {
  return useQuery({
    queryKey: [...trashKeys.list(state), page],
    queryFn: async () =>
      (
        await api.get<Paginated<TrashEntry>>('/trash', {
          params: { page, ...(state === 'all' ? {} : { state }) },
        })
      ).data,
  });
}

/** Remet un élément et tout ce qui partait avec lui ; l'application se relit ensuite. */
export function useRestore() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => (await api.post<TrashEntry>(`/trash/${id}/restore`)).data,
    onSuccess: () => {
      // Une restauration peut toucher n'importe quel écran : tout est relu.
      void client.invalidateQueries();
    },
  });
}
