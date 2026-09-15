import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { AfricaAnalytics, CountryAnalytics } from '@/api/types';
// useHealth vit dans src/api/hooks/useHealth.ts (contrat 4 clés, polling borné).

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
