import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';

const entry = {
  id: 't1',
  label: 'ALFA GH SR 10MG CPR B30 (SN)',
  kind: 'page du classeur',
  model: 'amm.marketingauthorization',
  object_id: 'amm-1',
  country: 'SN',
  reason: 'Page supprimée du classeur Cardio',
  rows: 5,
  deleted_by: 'Awa Diop',
  deleted_at: '2026-11-10T09:00:00Z',
  restored_by: null,
  restored_at: null,
};

describe('Corbeille', () => {
  it('liste ce qui a été supprimé et le restaure', async () => {
    loginAs('u-ceo');
    let restored = false;
    server.use(
      http.get('/api/v1/trash', () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [
            restored ? { ...entry, restored_at: '2026-11-10T10:00:00Z', restored_by: 'Awa Diop' } : entry,
          ],
        }),
      ),
      http.post('/api/v1/trash/t1/restore', () => {
        restored = true;
        return HttpResponse.json({ ...entry, restored_at: '2026-11-10T10:00:00Z' });
      }),
    );
    renderApp('/admin/corbeille');
    const table = await screen.findByTestId('trash-table', {}, { timeout: 5000 });
    expect(await within(table).findByText(/ALFA GH SR 10MG CPR B30/)).toBeInTheDocument();
    expect(within(table).getByText(/avec 4 éléments liés/)).toBeInTheDocument();
    await userEvent.click(within(table).getByRole('button', { name: /Restaurer/ }));
    await waitFor(() => expect(restored).toBe(true));
  });

  it("n'est pas proposée à un réglementaire pays", async () => {
    loginAs('u-sn');
    renderApp('/admin/corbeille');
    await waitFor(() => expect(screen.queryByTestId('trash-table')).not.toBeInTheDocument());
  });
});
