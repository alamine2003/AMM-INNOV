import axios, { type AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '@/features/auth/authStore';

export const API_BASE = `${import.meta.env.VITE_API_BASE ?? ''}/api/v1`;

// withCredentials : le refresh token est un cookie httpOnly limité à /api/v1/auth ; il n'est
// envoyé que sur les routes d'authentification (login, refresh, logout).
export const api = axios.create({ baseURL: API_BASE, timeout: 30000, withCredentials: true });

/** Client sans intercepteur, utilisé pour le refresh afin d'éviter les boucles. */
const bare = axios.create({ baseURL: API_BASE, timeout: 15000, withCredentials: true });

let refreshing: Promise<string | null> | null = null;

/** Obtient un nouveau jeton d'accès à partir du cookie de session ; null (et déconnexion) sinon. */
export async function refreshAccessToken(): Promise<string | null> {
  if (refreshing) return refreshing;
  const { setSession, logout } = useAuthStore.getState();
  refreshing = bare
    .post<{ access: string }>('/auth/refresh', {})
    .then((res) => {
      setSession({ access: res.data.access });
      return res.data.access;
    })
    .catch(() => {
      logout();
      return null;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const access = useAuthStore.getState().access;
  if (access) {
    config.headers.set('Authorization', `Bearer ${access}`);
  }
  return config;
});

type RetriableConfig = AxiosRequestConfig & { _retry?: boolean };

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined;
    const url = config?.url ?? '';
    const isAuthRoute = url.includes('/auth/login') || url.includes('/auth/refresh');
    if (error.response?.status === 401 && config && !config._retry && !isAuthRoute) {
      config._retry = true;
      const access = await refreshAccessToken();
      if (access) {
        config.headers = { ...(config.headers ?? {}), Authorization: `Bearer ${access}` };
        return api.request(config);
      }
      useAuthStore.getState().logout();
    }
    return Promise.reject(error);
  },
);

export function extractErrorMessage(error: unknown, fallback = 'Une erreur est survenue'): string {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    // Messages DRF par défaut en anglais (« No X matches the given query. », « Not found. ») :
    // on parle français à l'utilisateur, et un 404 sur un objet hors périmètre reste un 404.
    if (status === 404) return 'Élément introuvable ou hors de votre périmètre.';
    if (status !== undefined && status >= 500) return `Erreur serveur (${status}) — réessayez plus tard.`;
    if (!error.response && error.request) return 'Serveur injoignable — vérifiez votre connexion.';
    const data = error.response?.data as Record<string, unknown> | string | undefined;
    // Réponse non JSON (page HTML 404/502 du proxy) : ne pas afficher « 0 : < ».
    if (typeof data === 'string') {
      return error.response?.status
        ? `Erreur ${error.response.status} — ${error.response.statusText || fallback}`
        : fallback;
    }
    if (data) {
      if (typeof data.detail === 'string') return data.detail;
      if (typeof data.title === 'string') return data.title;
      if (typeof data.message === 'string') return data.message;
      const firstKey = Object.keys(data)[0];
      const first = firstKey ? data[firstKey] : undefined;
      if (Array.isArray(first) && typeof first[0] === 'string') return `${firstKey} : ${first[0]}`;
      if (typeof first === 'string') return `${firstKey} : ${first}`;
    }
    if (error.message) return error.message;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

export async function fetchBlob(url: string, params?: Record<string, unknown>): Promise<Blob> {
  const res = await api.get<Blob>(url, { responseType: 'blob', params });
  return res.data;
}
