import type { AlertFilters, AmmFilters } from './types';

export const queryKeys = {
  me: () => ['me'] as const,
  countries: {
    all: ['countries'] as const,
    list: () => ['countries', 'list'] as const,
    documents: (iso2: string, params?: Record<string, unknown>) =>
      ['countries', iso2, 'documents', params ?? {}] as const,
  },
  ranges: { all: ['ranges'] as const, list: () => ['ranges', 'list'] as const },
  products: {
    all: ['products'] as const,
    list: (params?: Record<string, unknown>) => ['products', 'list', params ?? {}] as const,
    detail: (id: string) => ['products', 'detail', id] as const,
    search: (search: string) => ['products', 'search', search] as const,
    documents: (id: string) => ['products', id, 'documents'] as const,
    coverage: (id: string) => ['products', id, 'coverage'] as const,
  },
  amms: {
    all: ['amms'] as const,
    list: (filters?: AmmFilters) => ['amms', 'list', filters ?? {}] as const,
    detail: (id: string) => ['amms', 'detail', id] as const,
    history: (id: string) => ['amms', id, 'history'] as const,
    renewals: (id: string) => ['amms', id, 'renewals'] as const,
    documents: (id: string, grouped = true) =>
      ['amms', id, 'documents', grouped ? 'period' : 'flat'] as const,
    alerts: (id: string) => ['amms', id, 'alerts'] as const,
  },
  renewals: { all: ['renewals'] as const },
  documents: {
    all: ['documents'] as const,
    library: (params: Record<string, unknown>) => ['documents', 'library', params] as const,
  },
  alerts: {
    all: ['alerts'] as const,
    list: (filters?: AlertFilters) => ['alerts', 'list', filters ?? {}] as const,
  },
  alertRules: { all: ['alert-rules'] as const },
  notifications: {
    all: ['notifications'] as const,
    list: (unread?: boolean) => ['notifications', 'list', { unread: !!unread }] as const,
    unreadCount: () => ['notifications', 'unread-count'] as const,
  },
  analytics: {
    all: ['analytics'] as const,
    africa: () => ['analytics', 'africa'] as const,
    country: (iso2: string) => ['analytics', 'country', iso2] as const,
    coverage: (productId: string) => ['analytics', 'coverage', productId] as const,
  },
  users: { all: ['users'] as const, list: () => ['users', 'list'] as const },
  imports: {
    all: ['imports'] as const,
    list: () => ['imports', 'list'] as const,
    detail: (id: string) => ['imports', 'detail', id] as const,
    rows: (id: string, outcome?: string, page?: number) =>
      ['imports', id, 'rows', outcome ?? 'ALL', page ?? 1] as const,
  },
  health: () => ['health'] as const,
};
