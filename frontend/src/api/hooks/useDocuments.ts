import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { AxiosProgressEvent } from 'axios';
import { api, fetchBlob } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { AmmDocument, DocumentKind, DocumentPeriod, Paginated } from '@/api/types';

export function useAmmDocumentsByPeriod(ammId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.amms.documents(ammId ?? '', true),
    queryFn: async () =>
      (await api.get<DocumentPeriod[]>(`/amms/${ammId}/documents`, { params: { group: 'period' } })).data,
    enabled: !!ammId,
  });
}

export function useCountryDocuments(iso2: string | undefined, params: { kind?: string; year?: string } = {}) {
  return useQuery({
    queryKey: queryKeys.countries.documents(iso2 ?? '', params),
    queryFn: async () => {
      const res = await api.get<Paginated<AmmDocument> | AmmDocument[]>(`/countries/${iso2}/documents`, {
        params: { page_size: 500, ...Object.fromEntries(Object.entries(params).filter(([, v]) => v)) },
      });
      return Array.isArray(res.data) ? res.data : res.data.results;
    },
    enabled: !!iso2,
  });
}

export interface UploadDocumentInput {
  file: File;
  kind: DocumentKind;
  document_date?: string;
  title?: string;
  /** null = AMM d'origine ; sinon identifiant de renouvellement. */
  renewalId?: string | null;
  onProgress?: (pct: number) => void;
}

function buildForm(input: Omit<UploadDocumentInput, 'renewalId' | 'onProgress'>): FormData {
  const form = new FormData();
  form.append('file', input.file);
  form.append('kind', input.kind);
  if (input.document_date) form.append('document_date', input.document_date);
  if (input.title) form.append('title', input.title);
  return form;
}

function progressHandler(onProgress?: (pct: number) => void) {
  return (e: AxiosProgressEvent) => {
    if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
  };
}

function useInvalidateDocuments(ammId: string) {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.amms.documents(ammId, true) });
    void qc.invalidateQueries({ queryKey: queryKeys.amms.detail(ammId) });
    void qc.invalidateQueries({ queryKey: queryKeys.amms.history(ammId) });
    void qc.invalidateQueries({ queryKey: queryKeys.amms.list() });
    void qc.invalidateQueries({ queryKey: queryKeys.documents.all });
    void qc.invalidateQueries({ queryKey: queryKeys.countries.all });
    void qc.invalidateQueries({ queryKey: queryKeys.products.all });
  };
}

export function useUploadDocument(ammId: string) {
  const invalidate = useInvalidateDocuments(ammId);
  return useMutation({
    mutationFn: async ({ renewalId, onProgress, ...rest }: UploadDocumentInput) => {
      const url = renewalId ? `/renewals/${renewalId}/documents` : `/amms/${ammId}/documents`;
      const res = await api.post<AmmDocument>(url, buildForm(rest), {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: progressHandler(onProgress),
      });
      return res.data;
    },
    onSuccess: invalidate,
  });
}

export function useReplaceDocument(ammId: string) {
  const invalidate = useInvalidateDocuments(ammId);
  return useMutation({
    mutationFn: async ({
      documentId,
      file,
      onProgress,
      ...rest
    }: {
      documentId: string;
      file: File;
      kind?: DocumentKind;
      document_date?: string;
      title?: string;
      onProgress?: (pct: number) => void;
    }) => {
      const form = new FormData();
      form.append('file', file);
      if (rest.kind) form.append('kind', rest.kind);
      if (rest.document_date) form.append('document_date', rest.document_date);
      if (rest.title) form.append('title', rest.title);
      const res = await api.post<AmmDocument>(`/documents/${documentId}/replace`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: progressHandler(onProgress),
      });
      return res.data;
    },
    onSuccess: invalidate,
  });
}

export function useDeleteDocument(ammId: string) {
  const invalidate = useInvalidateDocuments(ammId);
  return useMutation({
    mutationFn: async (documentId: string) => {
      await api.delete(`/documents/${documentId}`);
    },
    onSuccess: invalidate,
  });
}

export const fetchDocumentBlob = (documentId: string, download = false) =>
  fetchBlob(`/documents/${documentId}/file`, download ? { download: 1 } : undefined);

export const fetchAmmArchive = (ammId: string) => fetchBlob(`/amms/${ammId}/documents/archive.zip`);

export function documentFileName(doc: AmmDocument, countryIso2?: string, productName?: string): string {
  const base = [countryIso2, productName, doc.kind, doc.document_date].filter(Boolean).join('_');
  return `${base || doc.title || doc.id}.pdf`.replace(/[\\/:*?"<>|\s]+/g, '_');
}
