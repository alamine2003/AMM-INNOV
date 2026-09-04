import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { Paginated, User, UserWrite } from '@/api/types';

export function useUsers(enabled = true) {
  return useQuery({
    queryKey: queryKeys.users.list(),
    queryFn: async () => {
      const res = await api.get<Paginated<User> | User[]>('/users', { params: { page_size: 500 } });
      return Array.isArray(res.data) ? res.data : res.data.results;
    },
    enabled,
  });
}

export function useUserMutations() {
  const qc = useQueryClient();
  const onSuccess = () => qc.invalidateQueries({ queryKey: queryKeys.users.all });
  const create = useMutation({
    mutationFn: async (payload: UserWrite) => (await api.post<User>('/users', payload)).data,
    onSuccess,
  });
  const update = useMutation({
    mutationFn: async ({ id, ...payload }: Partial<UserWrite> & { id: string }) =>
      (await api.patch<User>(`/users/${id}`, payload)).data,
    onSuccess,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/users/${id}`);
    },
    onSuccess,
  });
  return { create, update, remove };
}
