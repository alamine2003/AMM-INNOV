import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, fetchBlob } from '@/api/client';
import type { DossierImportBatch, Paginated } from '@/api/types';
import { createFolderFormData, type FolderFile } from '@/features/dossier-imports/folderUpload';

export const dossierImportKeys = {
  all: ['dossier-imports'] as const,
  list: (page: number) => ['dossier-imports', 'list', page] as const,
  detail: (id: string) => ['dossier-imports', 'detail', id] as const,
};

export function useDossierImports(page: number) {
  return useQuery({
    queryKey: dossierImportKeys.list(page),
    queryFn: async () =>
      (await api.get<Paginated<DossierImportBatch>>('/dossier-imports', { params: { page, page_size: 20 } }))
        .data,
    placeholderData: keepPreviousData,
  });
}

export function useDossierImport(id: string | undefined) {
  return useQuery({
    queryKey: dossierImportKeys.detail(id ?? ''),
    queryFn: async () => (await api.get<DossierImportBatch>(`/dossier-imports/${id}`)).data,
    enabled: !!id,
    refetchInterval: (query) =>
      ['PENDING', 'RUNNING'].includes(query.state.data?.status ?? '') ? 2000 : false,
  });
}

export function useUploadDossier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ files, onProgress }: { files: FolderFile[]; onProgress: (value: number) => void }) =>
      (
        await api.post<DossierImportBatch>('/dossier-imports', createFolderFormData(files), {
          timeout: 180000,
          onUploadProgress: ({ loaded, total }) => total && onProgress(Math.round((loaded / total) * 100)),
        })
      ).data,
    onSuccess: (batch) => {
      qc.setQueryData(dossierImportKeys.detail(batch.id), batch);
      void qc.invalidateQueries({ queryKey: dossierImportKeys.all });
    },
  });
}

export function useAnalyzeDossier(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { country?: string } = {}) =>
      (await api.post<DossierImportBatch>(`/dossier-imports/${id}/analyze`, payload)).data,
    onSuccess: (batch) => {
      qc.setQueryData(dossierImportKeys.detail(id), batch);
      void qc.invalidateQueries({ queryKey: dossierImportKeys.all });
    },
  });
}

export function useConfirmDossier(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { preview_token: string; accepted_changes: string[] }) =>
      (await api.post<DossierImportBatch>(`/dossier-imports/${id}/confirm`, payload)).data,
    onSuccess: (batch) => {
      qc.setQueryData(dossierImportKeys.detail(id), batch);
      for (const key of [
        'dossier-imports',
        'amms',
        'renewals',
        'documents',
        'products',
        'analytics',
        'alerts',
      ])
        void qc.invalidateQueries({ queryKey: [key] });
    },
  });
}

export function fetchDossierFile(batchId: string, fileId: string) {
  return fetchBlob(`/dossier-imports/${batchId}/file`, { file_id: fileId });
}
