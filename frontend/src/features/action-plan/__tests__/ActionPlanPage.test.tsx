import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';

const category = (gap: string, label: string, count: number, items: object[] = []) => ({
  gap,
  label,
  hint: `${label} : explication`,
  action: gap === 'no_original' ? 'Compléter l’origine' : 'Ajouter le scan',
  count,
  items,
});

const item = {
  id: 'amm-1',
  product_name: 'ARTEGEN 120MG PDRE SOL INJ',
  country_iso2: 'SN',
  country_name: 'Sénégal',
  status: 'EXPIRE',
  effective_end_date: '2026-01-10',
  original_number: '',
  original_start_date: null,
};

describe("Plan d'action", () => {
  it('liste les AMM à compléter par manque, avec l’action qui mène au bon onglet', async () => {
    loginAs('u-hq');
    server.use(
      http.get('/api/v1/amms/action-plan', () =>
        HttpResponse.json({
          total: 12,
          categories: [
            category('no_original', 'Origine non identifiée', 12, [item]),
            category('missing_renewal', 'Sans renouvellement', 0),
          ],
        }),
      ),
    );
    renderApp('/plan-action');
    const row = await screen.findByTestId('plan-item-no_original', {}, { timeout: 5000 });
    expect(within(row).getByText('ARTEGEN 120MG PDRE SOL INJ')).toBeInTheDocument();
    expect(within(row).getByRole('link', { name: 'Compléter l’origine' })).toHaveAttribute(
      'href',
      '/amms/amm-1?tab=detail',
    );
    expect(screen.getByTestId('plan-count-no_original')).toHaveTextContent('12');
    expect(screen.getByText('Rien à faire ici.')).toBeInTheDocument();
    // Plus d'AMM que la carte n'en montre : la liste filtrée prend le relais.
    expect(screen.getByRole('link', { name: 'Voir les 12 dans la liste des AMM' })).toHaveAttribute(
      'href',
      '/amms?gap=no_original',
    );
    expect(screen.getByText('12 AMM à compléter')).toBeInTheDocument();
  });

  it('est dans le menu de chacun, réglementaire pays compris', async () => {
    loginAs('u-sn');
    renderApp('/plan-action');
    expect(
      await screen.findByRole('heading', { name: "Plan d'action" }, { timeout: 5000 }),
    ).toBeInTheDocument();
  });
});
