import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { ErrorEvent, Paginated } from '@/api/types';

export type ErrorState = 'open' | 'resolved' | 'all';

/** Journal des erreurs (CEO) : les plus récentes d'abord. */
export function useErrors(state: ErrorState, page = 1) {
  return useQuery({
    queryKey: ['errors', state, page],
    queryFn: async () =>
      (
        await api.get<Paginated<ErrorEvent>>('/errors', {
          params: { page, ...(state === 'all' ? {} : { state }) },
        })
      ).data,
    placeholderData: keepPreviousData,
  });
}

export function useResolveError() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => (await api.post<ErrorEvent>(`/errors/${id}/resolve`)).data,
    onSuccess: () => void client.invalidateQueries({ queryKey: ['errors'] }),
  });
}
