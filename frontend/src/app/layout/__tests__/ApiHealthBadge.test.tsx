import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { onlineManager } from '@tanstack/react-query';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import type { Health } from '@/api/types';
import { HEALTH_POLL_MS } from '@/api/hooks/useHealth';
import { ApiHealthBadge } from '@/app/layout/ApiHealthBadge';
import { server } from '@/mocks/server';
import { loginAs, renderApp, renderWithProviders } from '@/test/utils';

const HEALTH_URL = '/api/v1/health';

async function badge() {
  return screen.findByTestId('api-health-badge', {}, { timeout: 5000 });
}

describe('ApiHealthBadge', () => {
  it('affiche « API en ligne · mock » avec le handler MSW par défaut (conforme au contrat)', async () => {
    renderWithProviders(<ApiHealthBadge />);
    const el = await badge();
    await waitFor(() => expect(el).toHaveAttribute('data-status', 'online'));
    expect(el).toHaveTextContent('API en ligne · mock');
    expect(el.className).not.toMatch(/MuiChip-colorError/);
  });

  it('affiche la version renvoyée par un 200 nominal', async () => {
    server.use(
      http.get(HEALTH_URL, () =>
        HttpResponse.json({ status: 'ok', database: true, redis: true, version: '1.4.2' } satisfies Health),
      ),
    );
    renderWithProviders(<ApiHealthBadge />);
    const el = await badge();
    await waitFor(() => expect(el).toHaveTextContent('API en ligne · 1.4.2'));
  });

  it('affiche « dégradée » en rouge (MuiChip-colorError) sur un 503 status "degraded"', async () => {
    server.use(
      http.get(HEALTH_URL, () =>
        HttpResponse.json(
          { status: 'degraded', database: false, redis: true, version: '1.4.2' } satisfies Health,
          { status: 503 },
        ),
      ),
    );
    renderWithProviders(<ApiHealthBadge />);
    const el = await badge();
    await waitFor(() => expect(el).toHaveAttribute('data-status', 'degraded'));
    expect(el).toHaveTextContent('API dégradée · 1.4.2');
    expect(el).toHaveClass('MuiChip-colorError');
  });

  it.each<[string, () => void]>([
    ['une erreur réseau', () => server.use(http.get(HEALTH_URL, () => HttpResponse.error()))],
    [
      'un 502 HTML (proxy en panne)',
      () =>
        server.use(
          http.get(
            HEALTH_URL,
            () =>
              new HttpResponse('<html>Bad Gateway</html>', {
                status: 502,
                headers: { 'Content-Type': 'text/html' },
              }),
          ),
        ),
    ],
    [
      'un 503 au corps non conforme',
      () => server.use(http.get(HEALTH_URL, () => HttpResponse.json({ detail: 'x' }, { status: 503 }))),
    ],
  ])('affiche « injoignable » sur %s', async (_label, setup) => {
    setup();
    renderWithProviders(<ApiHealthBadge />);
    const el = await badge();
    await waitFor(() => expect(el).toHaveAttribute('data-status', 'unreachable'));
    expect(el).toHaveTextContent('API injoignable');
    expect(el).not.toHaveClass('MuiChip-colorError');
  });

  it('bascule en injoignable après un succès : jamais un « en ligne » périmé', async () => {
    const { queryClient } = renderWithProviders(<ApiHealthBadge />);
    const el = await badge();
    await waitFor(() => expect(el).toHaveAttribute('data-status', 'online'));
    server.use(http.get(HEALTH_URL, () => HttpResponse.error()));
    await queryClient.refetchQueries({ queryKey: queryKeys.health() });
    await waitFor(() => expect(el).toHaveAttribute('data-status', 'unreachable'));
  });

  it('affiche « version inconnue » sur un 200 sans champ version (déploiement Netlify avant Railway)', async () => {
    server.use(http.get(HEALTH_URL, () => HttpResponse.json({ status: 'ok', database: true, redis: true })));
    renderWithProviders(<ApiHealthBadge />);
    const el = await badge();
    await waitFor(() => expect(el).toHaveTextContent('API en ligne · version inconnue'));
  });

  it("reste « en ligne » quand redis est indisponible, et le dit dans l'infobulle", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(HEALTH_URL, () =>
        HttpResponse.json({ status: 'ok', database: true, redis: false, version: '1.4.2' } satisfies Health),
      ),
    );
    renderWithProviders(<ApiHealthBadge />);
    const el = await badge();
    await waitFor(() => expect(el).toHaveAttribute('data-status', 'online'));
    await user.hover(el);
    const tooltip = await screen.findByRole('tooltip', {}, { timeout: 5000 });
    expect(tooltip).toHaveTextContent('Redis : indisponible');
  });

  it("garde la version complète (64 caractères) dans l'infobulle", async () => {
    const user = userEvent.setup();
    const longVersion = 'a'.repeat(64);
    server.use(
      http.get(HEALTH_URL, () =>
        HttpResponse.json({
          status: 'ok',
          database: true,
          redis: true,
          version: longVersion,
        } satisfies Health),
      ),
    );
    renderWithProviders(<ApiHealthBadge />);
    const el = await badge();
    await waitFor(() => expect(el).toHaveAttribute('data-status', 'online'));
    await user.hover(el);
    const tooltip = await screen.findByRole('tooltip', {}, { timeout: 5000 });
    expect(tooltip).toHaveTextContent(`Version déployée : ${longVersion}`);
  });

  it('sonde quand même hors ligne (networkMode "always") : jamais bloqué en "checking"', async () => {
    server.use(http.get(HEALTH_URL, () => HttpResponse.error()));
    onlineManager.setOnline(false);
    try {
      renderWithProviders(<ApiHealthBadge />);
      const el = await badge();
      await waitFor(() => expect(el).toHaveAttribute('data-status', 'unreachable'));
    } finally {
      onlineManager.setOnline(true);
    }
  });

  it('appelle /health avec un délai de requête de 5 000 ms', async () => {
    const spy = vi.spyOn(api, 'get');
    renderWithProviders(<ApiHealthBadge />);
    await badge();
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith('/health', expect.objectContaining({ timeout: 5000 })),
    );
  });

  it('sonde une fois puis relance après 60 s (horloge simulée)', async () => {
    let calls = 0;
    server.use(
      http.get(HEALTH_URL, () => {
        calls += 1;
        return HttpResponse.json({
          status: 'ok',
          database: true,
          redis: true,
          version: 'mock',
        } satisfies Health);
      }),
    );
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      renderWithProviders(<ApiHealthBadge />);
      await vi.waitFor(() => expect(calls).toBe(1));
      await vi.advanceTimersByTimeAsync(HEALTH_POLL_MS);
      await vi.waitFor(() => expect(calls).toBe(2));
    } finally {
      vi.useRealTimers();
    }
  });

  it('apparaît dans la barre du haut pour un rôle restreint (u-sn)', async () => {
    loginAs('u-sn');
    renderApp('/');
    await badge();
  });

  it("n'affiche aucun badge et ne sonde pas /health sur /login sans session", async () => {
    let calls = 0;
    server.use(
      http.get(HEALTH_URL, () => {
        calls += 1;
        return HttpResponse.json({
          status: 'ok',
          database: true,
          redis: true,
          version: 'mock',
        } satisfies Health);
      }),
    );
    renderApp('/login');
    await screen.findByLabelText(/adresse e-mail/i);
    expect(screen.queryByTestId('api-health-badge')).not.toBeInTheDocument();
    expect(calls).toBe(0);
  });
});
