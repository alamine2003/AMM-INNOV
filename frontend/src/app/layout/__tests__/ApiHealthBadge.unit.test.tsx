import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toApiHealthState, type ApiHealthState } from '@/api/hooks/useHealth';
import { ApiHealthBadgeView } from '@/app/layout/ApiHealthBadge';
import type { Health } from '@/api/types';
import { renderWithProviders } from '@/test/utils';

// Complète les tests livrés par dev-frontend (ApiHealthBadge.test.tsx, useHealth.test.ts) sans les
// dupliquer : combinaison défensive de toApiHealthState, libellés courts ET longs simultanément
// visibles dans le DOM jsdom (aucune media query réellement évaluée), état « online » sans donnée
// exploitable, et confirmation que `health` est bien ignoré en `unreachable` (docstring de
// ApiHealthBadgeViewProps).

describe('toApiHealthState — combinaison défensive', () => {
  it('reste "online" sur un succès sans donnée (query.data undefined) : ne bascule jamais sur "degraded" par défaut', () => {
    expect(toApiHealthState({ status: 'success' })).toBe('online');
  });
});

describe('ApiHealthBadgeView — libellés courts et longs', () => {
  it.each<[ApiHealthState, string, string]>([
    ['checking', "Vérification de l'API…", 'API…'],
    ['unreachable', 'API injoignable', 'Injoignable'],
  ])('affiche le libellé long "%s" et le libellé court "%s" pour l\'état %s', (state, long, short) => {
    renderWithProviders(<ApiHealthBadgeView state={state} />);
    expect(screen.getByText(long)).toBeInTheDocument();
    expect(screen.getByText(short)).toBeInTheDocument();
  });

  it('online : libellé long "API en ligne · 1.4.2" et libellé court "En ligne" coexistent', () => {
    const health: Health = { status: 'ok', database: true, redis: true, version: '1.4.2' };
    renderWithProviders(<ApiHealthBadgeView state="online" health={health} />);
    expect(screen.getByText('API en ligne · 1.4.2')).toBeInTheDocument();
    expect(screen.getByText('En ligne')).toBeInTheDocument();
  });

  it('degraded : libellé long "API dégradée · 1.4.2" et libellé court "Dégradée" coexistent', () => {
    const health: Health = { status: 'degraded', database: false, redis: true, version: '1.4.2' };
    renderWithProviders(<ApiHealthBadgeView state="degraded" health={health} />);
    expect(screen.getByText('API dégradée · 1.4.2')).toBeInTheDocument();
    expect(screen.getByText('Dégradée')).toBeInTheDocument();
  });
});

describe('ApiHealthBadgeView — cas limites', () => {
  it('online sans donnée exploitable (health undefined) : « version inconnue », jamais de trace de version périmée', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ApiHealthBadgeView state="online" />);
    const badge = screen.getByTestId('api-health-badge');
    expect(badge).toHaveAttribute('data-status', 'online');
    expect(badge).toHaveTextContent('API en ligne · version inconnue');
    expect(badge.className).not.toMatch(/MuiChip-colorError/);

    await user.hover(badge);
    const tooltip = await screen.findByRole('tooltip', {}, { timeout: 5000 });
    expect(tooltip).toHaveTextContent('Version déployée : version inconnue');
    expect(tooltip).toHaveTextContent('Base de données : indisponible');
    expect(tooltip).toHaveTextContent('Redis : indisponible');
  });

  it('unreachable ignore une donnée `health` fournie malgré tout (jamais un « en ligne » périmé affiché)', async () => {
    const user = userEvent.setup();
    const stale: Health = { status: 'ok', database: true, redis: true, version: '1.4.2' };
    renderWithProviders(<ApiHealthBadgeView state="unreachable" health={stale} />);
    const badge = screen.getByTestId('api-health-badge');
    expect(badge).toHaveAttribute('data-status', 'unreachable');
    expect(badge).toHaveTextContent('API injoignable');
    expect(screen.queryByText(/1\.4\.2/)).not.toBeInTheDocument();
    expect(badge.className).not.toMatch(/MuiChip-colorError/);

    await user.hover(badge);
    const tooltip = await screen.findByRole('tooltip', {}, { timeout: 5000 });
    expect(tooltip).toHaveTextContent(
      "Aucune réponse exploitable de l'API (réseau coupé, délai de 5 s dépassé ou service arrêté).",
    );
  });

  it('checking : aucune donnée à afficher, pas de rouge, pastille non conclusive', () => {
    renderWithProviders(<ApiHealthBadgeView state="checking" />);
    const badge = screen.getByTestId('api-health-badge');
    expect(badge).toHaveAttribute('data-status', 'checking');
    expect(badge.className).not.toMatch(/MuiChip-colorError/);
  });
});
