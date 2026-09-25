import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, fetchBlob } from '@/api/client';
import type { DossierImportBatch, DossierReviewPoint, Paginated } from '@/api/types';
import { createFolderFormData, fileDigest, type FolderFile } from '@/features/dossier-imports/folderUpload';

/**
 * Un lot envoyé mais pas encore analysé a un aperçu vide (`{}`) : on le traite comme absent pour
 * que l'historique et la fiche du lot n'essaient pas de lire `preview.amm`.
 */
export function withPreview(batch: DossierImportBatch): DossierImportBatch {
  const preview: unknown = batch.preview;
  const ready = !!preview && typeof preview === 'object' && 'amm' in preview && !!preview.amm;
  return { ...batch, preview: ready ? batch.preview : null };
}

export const dossierImportKeys = {
  all: ['dossier-imports'] as const,
  list: (page: number) => ['dossier-imports', 'list', page] as const,
  detail: (id: string) => ['dossier-imports', 'detail', id] as const,
};

export function useDossierImports(page: number) {
  return useQuery({
    queryKey: dossierImportKeys.list(page),
    queryFn: async () => {
      const data = (
        await api.get<Paginated<DossierImportBatch>>('/dossier-imports', { params: { page, page_size: 20 } })
      ).data;
      return { ...data, results: data.results.map(withPreview) };
    },
    placeholderData: keepPreviousData,
  });
}

export function useDossierImport(id: string | undefined) {
  return useQuery({
    queryKey: dossierImportKeys.detail(id ?? ''),
    queryFn: async () => withPreview((await api.get<DossierImportBatch>(`/dossier-imports/${id}`)).data),
    enabled: !!id,
    refetchInterval: (query) =>
      ['PENDING', 'RUNNING'].includes(query.state.data?.status ?? '') ? 2000 : false,
  });
}

/** Empreintes déjà envoyées pendant cette session (évite de redemander au serveur). */
const sentDigests = new Set<string>();

/** Fichiers que le serveur possède déjà, par chemin → empreinte ; vide en cas d'erreur. */
async function alreadySent(files: FolderFile[]): Promise<{ reused: Map<string, string>; digests: string[] }> {
  const digests = await Promise.all(files.map(({ file }) => fileDigest(file)));
  const unknown = [...new Set(digests.filter((d): d is string => !!d && !sentDigests.has(d)))];
  if (unknown.length) {
    try {
      const { data } = await api.post<{ known: string[] }>('/dossier-imports/known-files', {
        sha256: unknown,
      });
      data.known.forEach((digest) => sentDigests.add(digest));
    } catch {
      // Sans réponse du serveur, tout est envoyé normalement.
    }
  }
  const reused = new Map<string, string>();
  files.forEach(({ path }, index) => {
    const digest = digests[index];
    if (digest && sentDigests.has(digest)) reused.set(path, digest);
  });
  return { reused, digests: digests.filter((d): d is string => !!d) };
}

export function useUploadDossier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      files,
      onProgress,
    }: {
      files: FolderFile[];
      onProgress: (value: number) => void;
    }) => {
      const { reused, digests } = await alreadySent(files);
      const send = async (skip: Map<string, string>) =>
        withPreview(
          (
            await api.post<DossierImportBatch>('/dossier-imports', createFolderFormData(files, skip), {
              timeout: 180000,
              onUploadProgress: ({ loaded, total }) =>
                total && onProgress(Math.round((loaded / total) * 100)),
            })
          ).data,
        );
      let batch: DossierImportBatch;
      try {
        batch = await send(reused);
      } catch (error) {
        // Fichier réutilisable disparu (autre compte, stockage vidé) : on renvoie tout, une fois.
        if (!reused.size) throw error;
        sentDigests.clear();
        batch = await send(new Map());
      }
      digests.forEach((digest) => sentDigests.add(digest));
      return batch;
    },
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
      withPreview((await api.post<DossierImportBatch>(`/dossier-imports/${id}/analyze`, payload)).data),
    onSuccess: (batch) => {
      qc.setQueryData(dossierImportKeys.detail(id), batch);
      void qc.invalidateQueries({ queryKey: dossierImportKeys.all });
    },
  });
}

/** Données touchées par un rangement : fiche AMM, renouvellements, documents, tableaux de bord. */
const AFFECTED = [
  'dossier-imports',
  'review-points',
  'amms',
  'renewals',
  'documents',
  'products',
  'analytics',
  'alerts',
];

function invalidateAffected(qc: ReturnType<typeof useQueryClient>) {
  for (const key of AFFECTED) void qc.invalidateQueries({ queryKey: [key] });
}

/** « Ranger les documents » (lot prêt) ou, pour le siège, créer l'AMM absente depuis le dossier. */
export function useConfirmDossier(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { preview_token: string; create_amm?: boolean }) =>
      withPreview((await api.post<DossierImportBatch>(`/dossier-imports/${id}/confirm`, payload)).data),
    onSuccess: (batch) => {
      qc.setQueryData(dossierImportKeys.detail(id), batch);
      invalidateAffected(qc);
    },
  });
}

/** Réponse à la question « c'est quelle AMM ? » : le dossier est relu puis rangé sur cette AMM. */
export function useChooseAmm(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ammId: string) =>
      withPreview(
        (await api.post<DossierImportBatch>(`/dossier-imports/${id}/choose-amm`, { amm_id: ammId })).data,
      ),
    onSuccess: (batch) => {
      qc.setQueryData(dossierImportKeys.detail(id), batch);
      invalidateAffected(qc);
    },
  });
}

export function fetchDossierFile(batchId: string, fileId: string) {
  return fetchBlob(`/dossier-imports/${batchId}/file`, { file_id: fileId });
}

export const reviewPointKeys = {
  list: (filters: { amm?: string; batch?: string; status?: string }) => ['review-points', filters] as const,
};

/** Points à vérifier plus tard d'une AMM (fiche) ou d'un lot. */
export function useReviewPoints(filters: { amm?: string; batch?: string; status?: 'OPEN' }, enabled = true) {
  return useQuery({
    queryKey: reviewPointKeys.list(filters),
    queryFn: async () =>
      (await api.get<DossierReviewPoint[]>('/dossier-review-points', { params: filters })).data,
    enabled,
  });
}

/** « Appliquer la valeur du scan » ou « Ignorer » un point. */
export function useResolveReviewPoint() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, action }: { id: string; action: 'apply' | 'ignore' }) =>
      (await api.post<DossierReviewPoint>(`/dossier-review-points/${id}/${action}`)).data,
    onSuccess: () => invalidateAffected(qc),
  });
}

export function fetchReviewPointFile(pointId: string) {
  return fetchBlob(`/dossier-review-points/${pointId}/file`);
}
