import { create } from 'zustand';
import type { User, UserAction } from '@/api/types';

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

/**
 * L'utilisateur peut-il faire cette action sensible ? La réponse vient du backend (`actions` de
 * `/me` et de la connexion, calculées par `apps/accounts/roles.py`) : les règles de rôles ne sont
 * pas recopiées dans l'interface.
 */
export const can = (user: User | null, action: UserAction) => !!user?.actions?.includes(action);

export function useCan(action: UserAction): boolean {
  return useAuthStore((state) => can(state.user, action));
}
