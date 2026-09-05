import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { LoginResponse, User } from '@/api/types';
import { useAuthStore } from '@/features/auth/authStore';

export function useLogin() {
  const setSession = useAuthStore((s) => s.setSession);
  return useMutation({
    mutationFn: async (payload: { email: string; password: string }) => {
      const res = await api.post<LoginResponse>('/auth/login', payload);
      return res.data;
    },
    onSuccess: (data) => setSession({ access: data.access, user: data.user }),
  });
}

export function useLogout() {
  const logout = useAuthStore((s) => s.logout);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      try {
        await api.post('/auth/logout', {}); // le cookie httpOnly est révoqué et effacé par l'API
      } catch {
        /* la déconnexion locale suffit */
      }
    },
    onSettled: () => {
      logout();
      qc.clear();
    },
  });
}

export function useMe(enabled = true) {
  const setUser = useAuthStore((s) => s.setUser);
  return useQuery({
    queryKey: queryKeys.me(),
    queryFn: async () => {
      const res = await api.get<User>('/me');
      setUser(res.data);
      return res.data;
    },
    enabled,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

/** Renvoie l'utilisateur courant depuis le store (source de vérité côté client). */
export function useCurrentUser() {
  return useAuthStore((s) => s.user);
}
