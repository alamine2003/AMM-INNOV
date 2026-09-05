import { create } from 'zustand';
import type { User } from '@/api/types';

const REFRESH_KEY = 'amm.refresh';

interface AuthState {
  access: string | null;
  refresh: string | null;
  user: User | null;
  hydrated: boolean;
  setSession: (payload: { access: string; refresh?: string | null; user?: User | null }) => void;
  setAccess: (access: string) => void;
  setUser: (user: User | null) => void;
  setHydrated: (hydrated: boolean) => void;
  logout: () => void;
}

function readRefresh(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

function writeRefresh(value: string | null) {
  try {
    if (value) localStorage.setItem(REFRESH_KEY, value);
    else localStorage.removeItem(REFRESH_KEY);
  } catch {
    /* stockage indisponible */
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  access: null,
  refresh: readRefresh(),
  user: null,
  hydrated: false,
  setSession: ({ access, refresh, user }) => {
    if (refresh !== undefined) writeRefresh(refresh);
    set((state) => ({
      access,
      refresh: refresh === undefined ? state.refresh : refresh,
      user: user === undefined ? state.user : user,
      hydrated: true,
    }));
  },
  setAccess: (access) => set({ access }),
  setUser: (user) => set({ user, hydrated: true }),
  setHydrated: (hydrated) => set({ hydrated }),
  logout: () => {
    writeRefresh(null);
    set({ access: null, refresh: null, user: null, hydrated: true });
  },
}));

export function canEditCountry(user: User | null, iso2: string | undefined): boolean {
  if (!user) return false;
  if (user.role !== 'COUNTRY_REGULATORY') return true;
  return !!iso2 && user.countries.includes(iso2);
}

export const isAdmin = (user: User | null) => user?.role === 'CEO_ADMIN';
export const isHqOrAdmin = (user: User | null) =>
  user?.role === 'CEO_ADMIN' || user?.role === 'HQ_REGULATORY';
