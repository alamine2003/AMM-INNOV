import axios, { type AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '@/features/auth/authStore';

export const API_BASE = `${import.meta.env.VITE_API_BASE ?? ''}/api/v1`;

export const api = axios.create({ baseURL: API_BASE, timeout: 30000 });

/** Client sans intercepteur, utilisé pour le refresh afin d'éviter les boucles. */
const bare = axios.create({ baseURL: API_BASE, timeout: 15000 });

let refreshing: Promise<string | null> | null = null;

export async function refreshAccessToken(): Promise<string | null> {
  if (refreshing) return refreshing;
  const { refresh, setAccess, logout } = useAuthStore.getState();
  if (!refresh) return null;
  refreshing = bare
    .post<{ access: string }>('/auth/refresh', { refresh })
    .then((res) => {
      setAccess(res.data.access);
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
    const data = error.response?.data as Record<string, unknown> | undefined;
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

export function fileUrlFromApi(path: string): string {
  if (path.startsWith('http')) return path;
  if (path.startsWith('/api/')) return `${import.meta.env.VITE_API_BASE ?? ''}${path}`;
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}
