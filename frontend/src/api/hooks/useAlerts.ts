import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { Alert, AlertFilters, AlertRule, Paginated } from '@/api/types';

export function useAlerts(filters: AlertFilters = {}) {
  return useQuery({
    queryKey: queryKeys.alerts.list(filters),
    queryFn: async () =>
      (
        await api.get<Paginated<Alert>>('/alerts', {
          params: Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== '' && v !== undefined)),
        })
      ).data,
    placeholderData: keepPreviousData,
  });
}

export function useAlertActions() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.alerts.all });
    void qc.invalidateQueries({ queryKey: queryKeys.amms.all });
  };
  const acknowledge = useMutation({
    mutationFn: async (id: string) => (await api.post<Alert>(`/alerts/${id}/acknowledge`)).data,
    onSuccess: invalidate,
  });
  const assign = useMutation({
    mutationFn: async ({ id, user_id }: { id: string; user_id: string }) =>
      (await api.post<Alert>(`/alerts/${id}/assign`, { user_id })).data,
    onSuccess: invalidate,
  });
  const resolve = useMutation({
    mutationFn: async ({ id, comment }: { id: string; comment: string }) =>
      (await api.post<Alert>(`/alerts/${id}/resolve`, { comment })).data,
    onSuccess: invalidate,
  });
  return { acknowledge, assign, resolve };
}

export function useAlertRules() {
  return useQuery({
    queryKey: queryKeys.alertRules.all,
    queryFn: async () => {
      const res = await api.get<Paginated<AlertRule> | AlertRule[]>('/alert-rules', {
        params: { page_size: 200 },
      });
      return Array.isArray(res.data) ? res.data : res.data.results;
    },
  });
}

export function useAlertRuleMutations() {
  const qc = useQueryClient();
  const onSuccess = () => qc.invalidateQueries({ queryKey: queryKeys.alertRules.all });
  const create = useMutation({
    mutationFn: async (payload: Omit<AlertRule, 'id'>) =>
      (await api.post<AlertRule>('/alert-rules', payload)).data,
    onSuccess,
  });
  const update = useMutation({
    mutationFn: async ({ id, ...payload }: Partial<AlertRule> & { id: string }) =>
      (await api.patch<AlertRule>(`/alert-rules/${id}`, payload)).data,
    onSuccess,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/alert-rules/${id}`);
    },
    onSuccess,
  });
  return { create, update, remove };
}
