import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';

describe('Suppression immédiate', () => {
  it('supprime une gamme sans question et propose « Annuler »', async () => {
    loginAs('u-hq');
    let restored = '';
    server.use(
      http.post('/api/v1/trash/:id/restore', ({ params }) => {
        restored = String(params.id);
        return HttpResponse.json({ id: params.id, restored_at: '2026-11-12T10:00:00Z' });
      }),
    );
    renderApp('/admin/ranges');
    const grid = await screen.findByRole('grid', {}, { timeout: 5000 });
    const before = (await within(grid).findAllByRole('button', { name: 'Supprimer' })).length;
    await userEvent.click(within(grid).getAllByRole('button', { name: 'Supprimer' })[0]);
    // Aucune boîte de confirmation : le message de corbeille arrive directement.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(await screen.findByText(/mise à la corbeille/)).toBeInTheDocument();
    await waitFor(() =>
      expect(within(grid).getAllByRole('button', { name: 'Supprimer' }).length).toBe(before - 1),
    );
    await userEvent.click(screen.getByTestId('undo-delete'));
    await waitFor(() => expect(restored).toMatch(/^trash-/));
  });
});
