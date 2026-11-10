import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';

const base = {
  user_id: 'u-hq',
  object_id: 'amm-1',
  country: 'SN',
  reason: '',
  changes: [],
  rows: 1,
};

describe('Audit', () => {
  it('montre qui a fait quoi et filtre par action', async () => {
    loginAs('u-hq');
    const asked: string[] = [];
    server.use(
      http.get('/api/v1/audit/filters', () =>
        HttpResponse.json({
          types: [{ value: 'amm.MarketingAuthorization', label: 'AMM' }],
          actions: [
            { value: 'updated', label: 'Modification' },
            { value: 'deleted', label: 'Mise à la corbeille' },
          ],
          people: [{ id: 'u-hq', name: 'Moussa Ndiaye', active: true }],
        }),
      ),
      http.get('/api/v1/audit', ({ request }) => {
        asked.push(new URL(request.url).search);
        return HttpResponse.json({
          count: 2,
          page: 1,
          pages: 1,
          results: [
            {
              ...base,
              id: 'h1',
              at: '2026-11-10T09:00:00Z',
              action: 'updated',
              action_label: 'Modification',
              user: 'Moussa Ndiaye',
              model: 'amm.MarketingAuthorization',
              type: 'AMM',
              label: 'ALFA GH SR 10MG CPR B30 (SN)',
              changes: [{ field: 'notes', old: null, new: 'Vu au classeur' }],
            },
            {
              ...base,
              id: 't1',
              at: '2026-11-10T08:00:00Z',
              action: 'deleted',
              action_label: 'Mise à la corbeille',
              user: 'Moussa Ndiaye',
              model: 'amm.Renewal',
              type: 'Renouvellement',
              label: 'R2',
              reason: 'Page supprimée',
              rows: 3,
            },
          ],
        });
      }),
    );
    renderApp('/admin/audit');
    const table = await screen.findByTestId('audit-table', {}, { timeout: 5000 });
    expect(await within(table).findByText(/ALFA GH SR 10MG CPR B30/)).toBeInTheDocument();
    expect(within(table).getByText(/Vu au classeur/)).toBeInTheDocument();
    expect(within(table).getByText(/Page supprimée · avec 2 éléments liés/)).toBeInTheDocument();
    await waitFor(() => expect(asked.length).toBeGreaterThan(0));
  });

  it("n'est pas proposé à un réglementaire pays", async () => {
    loginAs('u-sn');
    renderApp('/admin/audit');
    expect(await screen.findByTestId('forbidden', {}, { timeout: 5000 })).toBeInTheDocument();
  });
});
