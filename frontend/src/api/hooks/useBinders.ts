import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, fetchBlob } from '@/api/client';
import type {
  BinderCorrection,
  BinderDetail,
  BinderExtraPage,
  BinderResult,
  BinderSummary,
} from '@/api/types';

export const binderKeys = {
  all: ['binders'] as const,
  shelf: ['binders', 'shelf'] as const,
  detail: (key: string) => ['binders', 'detail', key] as const,
};

/** Les classeurs visibles : le siège voit tout, un pays ne voit que les siens. */
export function useBinders() {
  return useQuery({
    queryKey: binderKeys.shelf,
    queryFn: async () => (await api.get<BinderSummary[]>('/binders')).data,
  });
}

export function useBinder(key: string | undefined) {
  return useQuery({
    queryKey: binderKeys.detail(key ?? ''),
    queryFn: async () => (await api.get<BinderDetail>(`/binders/${key}`)).data,
    enabled: !!key,
  });
}

export interface CheckPayload {
  amm: string;
  result: BinderResult;
  corrections?: BinderCorrection[];
  note?: string;
}

/** Chaque action renvoie le classeur à jour : il remplace le cache sans nouvelle requête. */
function useBinderMutation<T>(key: string, send: (payload: T) => Promise<BinderDetail>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: send,
    onSuccess: (binder) => {
      client.setQueryData(binderKeys.detail(key), binder);
      void client.invalidateQueries({ queryKey: binderKeys.shelf });
      void client.invalidateQueries({ queryKey: ['amms'] });
    },
  });
}

export function useCheckPage(key: string) {
  return useBinderMutation(
    key,
    async (payload: CheckPayload) =>
      (
        await api.post<BinderDetail>(`/binders/${key}/check`, {
          corrections: [],
          note: '',
          ...payload,
        })
      ).data,
  );
}

export function useUncheckPage(key: string) {
  return useBinderMutation(
    key,
    async (amm: string) => (await api.post<BinderDetail>(`/binders/${key}/uncheck`, { amm })).data,
  );
}

export function useExtraPages(key: string) {
  const client = useQueryClient();
  const refresh = () => {
    void client.invalidateQueries({ queryKey: binderKeys.detail(key) });
    void client.invalidateQueries({ queryKey: binderKeys.shelf });
  };
  const add = useMutation({
    mutationFn: async (payload: { product_name: string; note?: string }) =>
      (await api.post<BinderExtraPage>(`/binders/${key}/extras`, payload)).data,
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/binders/${key}/extras/${id}`);
    },
    onSuccess: refresh,
  });
  return { add, remove };
}

/** PDF du classeur, page par page (réservé au siège). */
export const fetchBinderPdf = (key: string) => fetchBlob(`/binders/${key}/pdf`);
