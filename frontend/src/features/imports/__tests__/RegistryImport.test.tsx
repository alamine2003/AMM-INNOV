import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { ImportBatch, ImportRow } from '@/api/types';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';

const batch: ImportBatch = {
  id: 'reg-1',
  status: 'DONE',
  dry_run: true,
  filename: '0_REGISTRE AMM GHPL.xlsx',
  created_at: '2026-09-28T09:00:00Z',
  summary: {
    kind: 'registry',
    dry_run: true,
    sheets: {
      'Registre GHPL — SENEGAL': { rows: 3, created: 1, updated: 1, skipped: 0, warnings: 1, errors: 0 },
    },
    totals: { rows: 3, created: 1, updated: 1, skipped: 0, warnings: 1, errors: 0 },
  },
};

const rows: ImportRow[] = [
  {
    sheet: 'Registre GHPL — SENEGAL',
    row_number: 4,
    raw: { Presentation: 'LOLIP 10MG CPR B/30' },
    outcome: 'WARNING',
    message: 'À vérifier : un acte classé du 13/01/2026 est plus récent que le Dashboard.',
  },
  {
    sheet: 'Registre GHPL — SENEGAL',
    row_number: 2,
    raw: { Presentation: 'OMEPRAL 20MG GELULE B28' },
    outcome: 'CREATED',
    message: 'Produit du catalogue repris : OMEPRAL 20MG GEL B/28; AMM créée.',
  },
];

describe('Import du registre GHPL', () => {
  it('ouvre sur les avertissements et filtre les lignes par résultat', async () => {
    loginAs('u-hq');
    server.use(
      http.get('/api/v1/imports/reg-1', () => HttpResponse.json(batch)),
      http.get('/api/v1/imports/reg-1/rows', ({ request }) => {
        const outcome = new URL(request.url).searchParams.get('outcome');
        const results = rows.filter((row) => row.outcome === outcome);
        return HttpResponse.json({ count: results.length, next: null, previous: null, results });
      }),
    );
    renderApp('/admin/imports/reg-1');
    expect(await screen.findByText('Registre GHPL')).toBeInTheDocument();
    expect(await screen.findByText(/plus récent que le Dashboard/)).toBeInTheDocument();
    const summary = screen.getAllByText('Registre GHPL — SENEGAL')[0].closest('tr')!;
    expect(
      within(summary)
        .getAllByRole('cell')
        .map((cell) => cell.textContent),
    ).toEqual(['Registre GHPL — SENEGAL', '1', '1', '1', '0']);
    await userEvent.click(screen.getByRole('button', { name: 'Créées' }));
    expect(await screen.findByText(/Produit du catalogue repris/)).toBeInTheDocument();
    expect(screen.queryByText(/plus récent que le Dashboard/)).not.toBeInTheDocument();
  });
});
