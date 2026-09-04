import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { AfricaAnalytics, CountryAnalytics } from '@/api/types';

export function useAfricaAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics.africa(),
    queryFn: async () => (await api.get<AfricaAnalytics>('/analytics/africa')).data,
  });
}

export function useCountryAnalytics(iso2: string | undefined) {
  return useQuery({
    queryKey: queryKeys.analytics.country(iso2 ?? ''),
    queryFn: async () => (await api.get<CountryAnalytics>(`/analytics/country/${iso2}`)).data,
    enabled: !!iso2,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: async () => (await api.get<{ status?: string }>('/health')).data,
    retry: false,
    staleTime: 60_000,
  });
}
