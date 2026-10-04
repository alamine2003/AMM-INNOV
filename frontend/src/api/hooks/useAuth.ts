import { useEffect, useRef } from 'react';
import axios from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { LoginResponse, User } from '@/api/types';
import { useAuthStore } from '@/features/auth/authStore';

/**
 * Démarrage du service : après une période sans visite, l'hébergeur met l'API en veille et la
 * première requête reste sans réponse (ou reçoit 502/503/504) le temps du redémarrage. La
 * connexion est alors retentée d'elle-même au lieu d'afficher une erreur.
 */
export const loginRetry = { delayMs: 6000, budgetMs: 120000 };

/** Vrai si l'API n'a pas répondu ou redémarre ; faux pour un refus (identifiants, quota…). */
export function isServiceStarting(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false;
  const status = error.response?.status;
  return status === undefined || status === 502 || status === 503 || status === 504;
}

export function useLogin() {
  const setSession = useAuthStore((s) => s.setSession);
  const started = useRef(0);
  return useMutation({
    mutationFn: async (payload: { email: string; password: string }) => {
      const res = await api.post<LoginResponse>('/auth/login', payload);
      return res.data;
    },
    onMutate: () => {
      started.current = Date.now();
    },
    retry: (_count, error) => isServiceStarting(error) && Date.now() - started.current < loginRetry.budgetMs,
    retryDelay: () => loginRetry.delayMs,
    onSuccess: (data) => setSession({ access: data.access, user: data.user }),
  });
}

/** Réveille l'API dès l'affichage de la page de connexion, pendant la saisie des identifiants. */
export function useWakeService() {
  useEffect(() => {
    void api.get('/health', { timeout: 100000 }).catch(() => undefined);
  }, []);
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
