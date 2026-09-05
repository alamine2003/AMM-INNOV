import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type {
  AmmDocument,
  CoverageCell,
  Country,
  DuplicateGroup,
  MergeDuplicatesResult,
  Paginated,
  Product,
  ProductRange,
} from '@/api/types';

/**
 * Charge toutes les pages d'un référentiel (l'API plafonne `page_size` à 500 : au-delà, les
 * produits de la fin de l'alphabet disparaissaient du sélecteur de la fiche AMM).
 */
async function fetchAll<T>(url: string, params: Record<string, unknown> = {}): Promise<T[]> {
  const items: T[] = [];
  for (let page = 1; page <= 20; page += 1) {
    const res = await api.get<Paginated<T> | T[]>(url, { params: { page_size: 500, ...params, page } });
    if (Array.isArray(res.data)) return res.data;
    items.push(...res.data.results);
    if (!res.data.next) break;
  }
  return items;
}

export function useCountries() {
  return useQuery({
    queryKey: queryKeys.countries.list(),
    queryFn: () => fetchAll<Country>('/countries'),
    staleTime: 10 * 60 * 1000,
  });
}

export function useRanges() {
  return useQuery({
    queryKey: queryKeys.ranges.list(),
    queryFn: () => fetchAll<ProductRange>('/ranges'),
    staleTime: 10 * 60 * 1000,
  });
}

export function useProducts(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: queryKeys.products.list(params),
    queryFn: () => fetchAll<Product>('/products', params),
  });
}

/** Recherche serveur (`?search=`), 20 résultats : évite de charger les 856 produits dans un sélecteur. */
export function useProductSearch(search: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.products.search(search),
    queryFn: async () =>
      (
        await api.get<Paginated<Product>>('/products', {
          params: { search: search || undefined, page_size: 20, ordering: 'name' },
        })
      ).data.results,
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

export function useProduct(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.products.detail(id ?? ''),
    queryFn: async () => (await api.get<Product>(`/products/${id}`)).data,
    enabled: !!id,
  });
}

export function useProductCoverage(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.analytics.coverage(id ?? ''),
    queryFn: async () => (await api.get<CoverageCell[]>(`/analytics/product/${id}/coverage`)).data,
    enabled: !!id,
  });
}

export function useProductDocuments(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.products.documents(id ?? ''),
    queryFn: () => fetchAll<AmmDocument>(`/products/${id}/documents`),
    enabled: !!id,
  });
}

function useCrud<T extends { id: string }>(resource: string, invalidate: readonly unknown[]) {
  const qc = useQueryClient();
  const onSuccess = () => qc.invalidateQueries({ queryKey: invalidate });
  const create = useMutation({
    mutationFn: async (payload: Partial<T>) => (await api.post<T>(`/${resource}`, payload)).data,
    onSuccess,
  });
  const update = useMutation({
    mutationFn: async ({ id, ...payload }: Partial<T> & { id: string }) =>
      (await api.patch<T>(`/${resource}/${id}`, payload)).data,
    onSuccess,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/${resource}/${id}`);
    },
    onSuccess,
  });
  return { create, update, remove };
}

export const useCountryMutations = () => useCrud<Country>('countries', queryKeys.countries.all);
export const useRangeMutations = () => useCrud<ProductRange>('ranges', queryKeys.ranges.all);
export const useProductMutations = () => useCrud<Product>('products', queryKeys.products.all);

/** Fusionne le produit `id` (doublon, supprimé) dans `target_id` (conservé). */
export function useMergeProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, target_id }: { id: string; target_id: string }) =>
      (await api.post<Product>(`/products/${target_id}/merge`, { duplicate_id: id })).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.products.all });
      void qc.invalidateQueries({ queryKey: queryKeys.amms.all });
    },
  });
}

/** Groupes de produits en doublon probable (même libellé à la ponctuation près). */
export function useProductDuplicates(enabled = true) {
  return useQuery({
    queryKey: queryKeys.products.duplicates(),
    queryFn: async () => (await api.get<DuplicateGroup[]>('/products/duplicates')).data,
    enabled,
    staleTime: 60_000,
  });
}

/** Fusionne tous les groupes sans conflit (CEO). */
export function useMergeDuplicates() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (dryRun: boolean) =>
      (await api.post<MergeDuplicatesResult>('/products/merge-duplicates', { dry_run: dryRun })).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.products.all });
      void qc.invalidateQueries({ queryKey: queryKeys.amms.all });
    },
  });
}
