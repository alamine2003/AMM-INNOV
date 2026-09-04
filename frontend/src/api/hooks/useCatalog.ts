import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { AmmDocument, CoverageCell, Country, Paginated, Product, ProductRange } from '@/api/types';

async function fetchAll<T>(url: string, params: Record<string, unknown> = {}): Promise<T[]> {
  const res = await api.get<Paginated<T> | T[]>(url, { params: { page_size: 500, ...params } });
  return Array.isArray(res.data) ? res.data : res.data.results;
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

export function useMergeProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, target_id }: { id: string; target_id: string }) =>
      (await api.post(`/products/${id}/merge`, { target_id })).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.products.all });
      void qc.invalidateQueries({ queryKey: queryKeys.amms.all });
    },
  });
}
