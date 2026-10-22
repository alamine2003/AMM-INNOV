import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { Paginated, Renewal, RenewalWrite, TransitionPayload } from '@/api/types';

export function useRenewals(ammId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.amms.renewals(ammId ?? ''),
    queryFn: async () => {
      const res = await api.get<Paginated<Renewal> | Renewal[]>(`/amms/${ammId}/renewals`);
      const list = Array.isArray(res.data) ? res.data : res.data.results;
      return [...list].sort((a, b) => b.sequence - a.sequence);
    },
    enabled: !!ammId,
  });
}

function useInvalidateAmm(ammId: string) {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.amms.renewals(ammId) });
    void qc.invalidateQueries({ queryKey: queryKeys.amms.detail(ammId) });
    void qc.invalidateQueries({ queryKey: queryKeys.amms.history(ammId) });
    void qc.invalidateQueries({ queryKey: queryKeys.amms.list() });
    void qc.invalidateQueries({ queryKey: queryKeys.alerts.all });
    void qc.invalidateQueries({ queryKey: queryKeys.analytics.all });
    // Les scans affichés par période et les classeurs suivent les renouvellements.
    void qc.invalidateQueries({ queryKey: queryKeys.amms.documents(ammId, true) });
    void qc.invalidateQueries({ queryKey: ['binders'] });
  };
}

/** Corrige un renouvellement (n°, dates, notes) : l'ordre et l'échéance de l'AMM sont recalculés. */
export function useUpdateRenewal(ammId: string) {
  const invalidate = useInvalidateAmm(ammId);
  return useMutation({
    mutationFn: async ({
      renewalId,
      ...payload
    }: RenewalWrite & { renewalId: string; end_date_manual?: boolean }) =>
      (await api.patch<Renewal>(`/renewals/${renewalId}`, payload)).data,
    onSuccess: invalidate,
  });
}

export function useCreateRenewal(ammId: string) {
  const invalidate = useInvalidateAmm(ammId);
  return useMutation({
    mutationFn: async (payload: RenewalWrite) =>
      (await api.post<Renewal>(`/amms/${ammId}/renewals`, payload)).data,
    onSuccess: invalidate,
  });
}

export function useDeleteRenewal(ammId: string) {
  const invalidate = useInvalidateAmm(ammId);
  return useMutation({
    mutationFn: async (renewalId: string) => {
      await api.delete(`/renewals/${renewalId}`);
    },
    onSuccess: invalidate,
  });
}

export function useTransitionRenewal(ammId: string) {
  const invalidate = useInvalidateAmm(ammId);
  return useMutation({
    mutationFn: async ({ renewalId, ...payload }: TransitionPayload & { renewalId: string }) =>
      (await api.post<Renewal>(`/renewals/${renewalId}/transition`, payload)).data,
    onSuccess: invalidate,
  });
}
