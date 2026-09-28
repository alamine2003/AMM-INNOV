import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, fetchBlob } from '@/api/client';
import type {
  DepositDetail,
  DepositEventKind,
  DepositSuggestion,
  DepositSummary,
  PieceType,
} from '@/api/types';

export const depositKeys = {
  all: ['deposits'] as const,
  list: ['deposits', 'list'] as const,
  suggestions: ['deposits', 'suggestions'] as const,
  detail: (id: string) => ['deposits', 'detail', id] as const,
  pieces: ['deposits', 'piece-types'] as const,
};

/** Dossiers visibles : le siège voit tout, un pays les siens. */
export function useDeposits() {
  return useQuery({
    queryKey: depositKeys.list,
    queryFn: async () => (await api.get<DepositSummary[]>('/deposits')).data,
  });
}

export function useDepositSuggestions(enabled = true) {
  return useQuery({
    queryKey: depositKeys.suggestions,
    queryFn: async () => (await api.get<DepositSuggestion[]>('/deposits/suggestions')).data,
    enabled,
  });
}

export function useDeposit(id: string | undefined) {
  return useQuery({
    queryKey: depositKeys.detail(id ?? ''),
    queryFn: async () => (await api.get<DepositDetail>(`/deposits/${id}`)).data,
    enabled: !!id,
  });
}

export function useOpenDeposit() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (amm: string) => (await api.post<DepositDetail>('/deposits', { amm })).data,
    onSuccess: (dossier) => {
      client.setQueryData(depositKeys.detail(dossier.id), dossier);
      void client.invalidateQueries({ queryKey: depositKeys.all });
      void client.invalidateQueries({ queryKey: ['amms'] });
    },
  });
}

/** Chaque action renvoie le dossier à jour : il remplace le cache. */
function useDepositAction<T>(id: string, send: (payload: T) => Promise<DepositDetail>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: send,
    onSuccess: (dossier) => {
      client.setQueryData(depositKeys.detail(id), dossier);
      void client.invalidateQueries({ queryKey: depositKeys.list });
      void client.invalidateQueries({ queryKey: ['amms'] });
      void client.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

function form(values: Record<string, string | File | null | undefined>) {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) {
    if (value !== null && value !== undefined && value !== '') data.append(key, value);
  }
  return data;
}

const post = async (url: string, body: unknown) => (await api.post<DepositDetail>(url, body)).data;

export function useDepositActions(id: string) {
  const base = `/deposits/${id}`;
  return {
    addPiece: useDepositAction(id, (p: { file: File; piece_type?: string; label?: string }) =>
      post(`${base}/pieces`, form(p)),
    ),
    removePiece: useDepositAction(
      id,
      async (pieceId: string) => (await api.delete<DepositDetail>(`${base}/pieces/${pieceId}`)).data,
    ),
    addSample: useDepositAction(
      id,
      (p: {
        batch_number: string;
        manufactured_on: string;
        expires_on: string;
        quantity?: number | null;
        note?: string;
      }) => post(`${base}/samples`, p),
    ),
    removeSample: useDepositAction(
      id,
      async (sampleId: string) => (await api.delete<DepositDetail>(`${base}/samples/${sampleId}`)).data,
    ),
    samplesRequired: useDepositAction(id, (required: boolean) =>
      post(`${base}/samples-required`, { required }),
    ),
    send: useDepositAction(id, (note: string) => post(`${base}/send`, { note })),
    deposit: useDepositAction(id, (p: { filing_date: string; file: File }) =>
      post(`${base}/deposit`, form(p)),
    ),
    addEvent: useDepositAction(
      id,
      (p: { kind: DepositEventKind; date: string; note?: string; file?: File | null }) =>
        post(`${base}/events`, form(p)),
    ),
    decide: useDepositAction(
      id,
      (p: {
        result: 'OBTENU' | 'REJETE';
        decision_date: string;
        number?: string;
        start_date?: string;
        note?: string;
        file?: File | null;
      }) => post(`${base}/decision`, form(p)),
    ),
    abandon: useDepositAction(id, (reason: string) => post(`${base}/abandon`, { reason })),
    message: useDepositAction(id, (body: string) => post(`${base}/messages`, { body })),
  };
}

export const depositFiles = {
  archive: (id: string) => fetchBlob(`/deposits/${id}/archive`),
  piece: (id: string, pieceId: string) => fetchBlob(`/deposits/${id}/pieces/${pieceId}/file`),
  event: (id: string, eventId: string) => fetchBlob(`/deposits/${id}/events/${eventId}/file`),
};

export function usePieceTypes() {
  return useQuery({
    queryKey: depositKeys.pieces,
    queryFn: async () => (await api.get<PieceType[]>('/deposit-pieces')).data,
  });
}

export function useSavePieceType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: Partial<PieceType> & { id?: string }) =>
      id
        ? (await api.patch<PieceType>(`/deposit-pieces/${id}`, body)).data
        : (await api.post<PieceType>('/deposit-pieces', body)).data,
    onSuccess: () => void client.invalidateQueries({ queryKey: depositKeys.all }),
  });
}

export function useDeletePieceType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/deposit-pieces/${id}`);
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: depositKeys.all }),
  });
}
