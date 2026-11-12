import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';

const event = {
  id: 'e1',
  source: 'server',
  source_label: 'Serveur',
  kind: 'KeyError',
  message: "'renewal'",
  detail: 'Traceback (most recent call last): …',
  location: 'GET api/v1/amms/<pk>',
  version: '1.2.5',
  count: 4,
  first_seen: '2026-11-11T08:00:00Z',
  last_seen: '2026-11-11T09:00:00Z',
  last_user: 'Moussa Ndiaye',
  resolved_at: null,
  resolved_by: null,
};

describe('Journal des erreurs', () => {
  it('liste les erreurs et en marque une résolue', async () => {
    loginAs('u-ceo');
    let resolved = false;
    server.use(
      http.get('/api/v1/errors', () =>
        HttpResponse.json({ count: 1, next: null, previous: null, results: [event] }),
      ),
      http.post('/api/v1/errors/e1/resolve', () => {
        resolved = true;
        return HttpResponse.json({ ...event, resolved_at: '2026-11-11T10:00:00Z' });
      }),
    );
    renderApp('/admin/erreurs');
    const table = await screen.findByTestId('errors-table', {}, { timeout: 5000 });
    expect(await within(table).findByText('KeyError')).toBeInTheDocument();
    expect(within(table).getByText('4')).toBeInTheDocument();
    await userEvent.click(within(table).getByRole('button', { name: 'Voir le détail' }));
    expect(await within(table).findByText(/Traceback/)).toBeInTheDocument();
    await userEvent.click(within(table).getByRole('button', { name: 'Résolue' }));
    await waitFor(() => expect(resolved).toBe(true));
  });

  it("n'est pas proposé au siège", async () => {
    loginAs('u-hq');
    renderApp('/admin/erreurs');
    expect(await screen.findByTestId('forbidden', {}, { timeout: 5000 })).toBeInTheDocument();
  });
});
