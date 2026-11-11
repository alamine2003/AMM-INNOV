import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { PermissionGrant, PermissionMatrix } from '@/api/types';

const key = ['permissions'] as const;

/** Rôles × actions (CEO). */
export function usePermissions() {
  return useQuery({
    queryKey: key,
    queryFn: async () => (await api.get<PermissionMatrix>('/permissions')).data,
  });
}

/** Enregistre les cases changées ; l'historique garde qui a changé quoi (audit). */
export function useSavePermissions() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (grants: PermissionGrant[]) =>
      (await api.put<PermissionMatrix>('/permissions', { grants })).data,
    onSuccess: (matrix) => {
      client.setQueryData(key, matrix);
      void client.invalidateQueries({ queryKey: ['audit'] });
    },
  });
}
