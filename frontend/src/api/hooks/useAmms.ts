import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { Alert, Amm, AmmFilters, AmmWrite, HistoryEntry, Paginated } from '@/api/types';

function cleanParams(filters: AmmFilters | Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  );
}

export function useAmms(filters: AmmFilters = {}) {
  return useQuery({
    queryKey: queryKeys.amms.list(filters),
    queryFn: async () => (await api.get<Paginated<Amm>>('/amms', { params: cleanParams(filters) })).data,
    placeholderData: keepPreviousData,
  });
}

export function useAmm(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.amms.detail(id ?? ''),
    queryFn: async () => (await api.get<Amm>(`/amms/${id}`)).data,
    enabled: !!id,
  });
}

export function useAmmHistory(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.amms.history(id ?? ''),
    queryFn: async () => (await api.get<HistoryEntry[]>(`/amms/${id}/history`)).data,
    enabled: !!id,
  });
}

export function useAmmAlerts(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.amms.alerts(id ?? ''),
    queryFn: async () => {
      const res = await api.get<Paginated<Alert> | Alert[]>('/alerts', {
        params: { amm: id, page_size: 200 },
      });
      return Array.isArray(res.data) ? res.data : res.data.results;
    },
    enabled: !!id,
  });
}

export function useCreateAmm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: AmmWrite) => (await api.post<Amm>('/amms', payload)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.amms.all });
      void qc.invalidateQueries({ queryKey: queryKeys.analytics.all });
    },
  });
}

export function useUpdateAmm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: Partial<AmmWrite> & { id: string }) =>
      (await api.patch<Amm>(`/amms/${id}`, payload)).data,
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.amms.detail(data.id), data);
      void qc.invalidateQueries({ queryKey: queryKeys.amms.all });
      void qc.invalidateQueries({ queryKey: queryKeys.analytics.all });
    },
  });
}

export async function exportAmms(filters: AmmFilters): Promise<Blob> {
  const res = await api.get<Blob>('/analytics/export', {
    params: { format: 'xlsx', ...cleanParams(filters) },
    responseType: 'blob',
  });
  return res.data;
}
