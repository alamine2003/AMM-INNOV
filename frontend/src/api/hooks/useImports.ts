import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { ImportBatch, ImportRow, Paginated } from '@/api/types';

export function useImports() {
  return useQuery({
    queryKey: queryKeys.imports.list(),
    queryFn: async () => {
      const res = await api.get<Paginated<ImportBatch> | ImportBatch[]>('/imports', {
        params: { page_size: 50 },
      });
      return Array.isArray(res.data) ? res.data : res.data.results;
    },
  });
}

export function useImport(id: string | undefined, poll = false) {
  return useQuery({
    queryKey: queryKeys.imports.detail(id ?? ''),
    queryFn: async () => (await api.get<ImportBatch>(`/imports/${id}`)).data,
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return poll && (status === 'PENDING' || status === 'RUNNING') ? 2000 : false;
    },
  });
}

export function useImportRows(id: string | undefined, outcome = 'ERROR', page = 1, pageSize = 50) {
  return useQuery({
    queryKey: queryKeys.imports.rows(id ?? '', outcome, page),
    queryFn: async () =>
      (
        await api.get<Paginated<ImportRow>>(`/imports/${id}/rows`, {
          params: { outcome, page, page_size: pageSize },
        })
      ).data,
    enabled: !!id,
    placeholderData: keepPreviousData,
  });
}

export function useStartImport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, onProgress }: { file: File; onProgress?: (pct: number) => void }) => {
      const form = new FormData();
      form.append('file', file);
      const res = await api.post<ImportBatch>('/imports', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
        },
      });
      return res.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.imports.all });
    },
  });
}
