import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, fetchBlob } from '@/api/client';
import type {
  BinderAddPageResult,
  BinderCorrection,
  BinderDetail,
  BinderExport,
  BinderExtraPage,
  BinderLocation,
  BinderPageScanResult,
  BinderResult,
  BinderSummary,
} from '@/api/types';

export const binderKeys = {
  all: ['binders'] as const,
  shelf: ['binders', 'shelf'] as const,
  detail: (key: string) => ['binders', 'detail', key] as const,
  exports: (key: string) => ['binders', 'exports', key] as const,
};

/** Les classeurs visibles : le siège voit tout, un pays ne voit que les siens. */
export function useBinders() {
  return useQuery({
    queryKey: binderKeys.shelf,
    queryFn: async () => (await api.get<BinderSummary[]>('/binders')).data,
    // Classeurs sortis par d'autres archivistes : l'étagère suit les allées et venues.
    refetchInterval: 30_000,
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

/** Préparations du classeur avec décisions officielles ; suivies tant qu'une est en cours. */
export function useBinderExports(key: string, enabled: boolean) {
  return useQuery({
    queryKey: binderKeys.exports(key),
    queryFn: async () => (await api.get<BinderExport[]>(`/binders/${key}/exports`)).data,
    enabled,
    refetchInterval: (query) =>
      query.state.data?.some((e) => e.status === 'PENDING' || e.status === 'RUNNING') ? 3000 : false,
  });
}

export function useStartBinderExport(key: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post<BinderExport>(`/binders/${key}/exports`)).data,
    onSuccess: () => void client.invalidateQueries({ queryKey: binderKeys.exports(key) }),
  });
}

export const fetchBinderExportFile = (key: string, exportId: string) =>
  fetchBlob(`/binders/${key}/exports/${exportId}/file`);

export interface AddPagePayload {
  product_name: string;
  range_code?: string | null;
  original_number?: string;
  original_start_date?: string | null;
  extra_id?: string | null;
}

/** Page oubliée : l'AMM est créée et prend sa place alphabétique dans le classeur. */
export function useAddPage(key: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (payload: AddPagePayload) =>
      (await api.post<BinderAddPageResult>(`/binders/${key}/pages`, payload)).data,
    onSuccess: (result) => {
      client.setQueryData(binderKeys.detail(result.binder_key), result.binder);
      void client.invalidateQueries({ queryKey: binderKeys.detail(key) });
      void client.invalidateQueries({ queryKey: binderKeys.shelf });
      void client.invalidateQueries({ queryKey: ['amms'] });
    },
  });
}

/** Scan déposé sur une page : envoyé comme un dossier rangé sur cette AMM. */
export function useImportPageScan(key: string) {
  return useMutation({
    mutationFn: async ({ amm, files }: { amm: string; files: File[] }) => {
      const form = new FormData();
      for (const file of files) form.append('files', file, file.name);
      return (await api.post<BinderPageScanResult>(`/binders/${key}/pages/${amm}/scan`, form)).data;
    },
  });
}

/** Signale que le classeur est ouvert (chaque minute) : l'étagère le montre sorti. */
export function useBinderPresence(key: string) {
  useEffect(() => {
    const ping = () => void api.post(`/binders/${key}/presence`).catch(() => undefined);
    ping();
    const timer = window.setInterval(ping, 60_000);
    return () => {
      window.clearInterval(timer);
      void api.delete(`/binders/${key}/presence`).catch(() => undefined);
    };
  }, [key]);
}

/** Classeur et page d'une AMM : relie la fiche AMM et les imports au classeur papier. */
export function useBinderLocation(ammId: string | null | undefined) {
  return useQuery({
    queryKey: [...binderKeys.all, 'locate', ammId ?? ''] as const,
    queryFn: async () => (await api.get<BinderLocation>('/binders/locate', { params: { amm: ammId } })).data,
    enabled: !!ammId,
    retry: false,
  });
}
