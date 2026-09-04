import type { ReactElement, ReactNode } from 'react';
import { render, type RenderOptions } from '@testing-library/react';
import { MemoryRouter, useRoutes } from 'react-router';
import { QueryClient } from '@tanstack/react-query';
import { AppProviders } from '@/app/providers';
import { routes } from '@/app/router';
import { useAuthStore } from '@/features/auth/authStore';
import { db } from '@/mocks/handlers';
import type { User } from '@/api/types';

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 }, mutations: { retry: false } },
  });
}

export function loginAs(userId: 'u-ceo' | 'u-hq' | 'u-sn' | 'u-ci'): User {
  const user = db.users.find((u) => u.id === userId)!;
  useAuthStore
    .getState()
    .setSession({ access: `mock-access-${userId}`, refresh: `mock-refresh-${userId}`, user });
  return user;
}

export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  const queryClient = makeQueryClient();
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <AppProviders queryClient={queryClient}>{children}</AppProviders>
  );
  return { queryClient, ...render(ui, { wrapper: Wrapper, ...options }) };
}

function TestRoutes() {
  return useRoutes(routes);
}

/** Rendu de l'application complète sur un MemoryRouter (pas de data router : évite les Request natives sous jsdom). */
export function renderApp(initialPath: string) {
  const queryClient = makeQueryClient();
  const result = render(
    <AppProviders queryClient={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <TestRoutes />
      </MemoryRouter>
    </AppProviders>,
  );
  return { queryClient, ...result };
}
