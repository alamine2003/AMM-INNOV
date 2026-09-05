import { create } from 'zustand';
import type { User } from '@/api/types';

/**
 * Session côté client : le jeton d'accès (15 min) vit en mémoire seulement ; le refresh token est
 * un cookie httpOnly posé par l'API, invisible au JavaScript. Au chargement, `RequireAuth` tente
 * un rafraîchissement silencieux avec ce cookie (`sessionChecked` évite de le retenter en boucle).
 */
interface AuthState {
  access: string | null;
  user: User | null;
  hydrated: boolean;
  sessionChecked: boolean;
  setSession: (payload: { access: string; user?: User | null }) => void;
  setAccess: (access: string) => void;
  setUser: (user: User | null) => void;
  setHydrated: (hydrated: boolean) => void;
  markSessionChecked: () => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  access: null,
  user: null,
  hydrated: false,
  sessionChecked: false,
  setSession: ({ access, user }) =>
    set((state) => ({
      access,
      user: user === undefined ? state.user : user,
      hydrated: true,
      sessionChecked: true,
    })),
  setAccess: (access) => set({ access, sessionChecked: true }),
  setUser: (user) => set({ user, hydrated: true }),
  setHydrated: (hydrated) => set({ hydrated }),
  markSessionChecked: () => set({ sessionChecked: true }),
  logout: () => set({ access: null, user: null, hydrated: true, sessionChecked: true }),
}));

export function canEditCountry(user: User | null, iso2: string | undefined): boolean {
  if (!user) return false;
  if (user.role !== 'COUNTRY_REGULATORY') return true;
  return !!iso2 && user.countries.includes(iso2);
}

export const isAdmin = (user: User | null) => user?.role === 'CEO_ADMIN';
export const isHqOrAdmin = (user: User | null) =>
  user?.role === 'CEO_ADMIN' || user?.role === 'HQ_REGULATORY';
