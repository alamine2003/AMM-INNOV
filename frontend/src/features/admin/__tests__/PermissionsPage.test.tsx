import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';

const roles = [
  { value: 'CEO_ADMIN', label: 'CEO / administrateur', editable: false },
  { value: 'HQ_REGULATORY', label: 'Réglementaire siège', editable: true },
  { value: 'COUNTRY_REGULATORY', label: 'Réglementaire pays', editable: true },
];
const matrix = {
  roles,
  actions: [
    {
      action: 'audit.view',
      group: 'Administration',
      label: "Consulter l'audit",
      locked: false,
      defaults: ['CEO_ADMIN', 'HQ_REGULATORY'],
      roles: { CEO_ADMIN: true, HQ_REGULATORY: true, COUNTRY_REGULATORY: false },
    },
    {
      action: 'permissions.manage',
      group: 'Administration',
      label: 'Régler les permissions',
      locked: true,
      defaults: ['CEO_ADMIN'],
      roles: { CEO_ADMIN: true, HQ_REGULATORY: false, COUNTRY_REGULATORY: false },
    },
  ],
};

describe('Permissions', () => {
  it('le CEO coche une case et enregistre seulement ce qui a changé', async () => {
    loginAs('u-ceo');
    let sent: unknown = null;
    server.use(
      http.get('/api/v1/permissions', () => HttpResponse.json(matrix)),
      http.put('/api/v1/permissions', async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json(matrix);
      }),
    );
    renderApp('/admin/permissions');
    const box = await screen.findByTestId('perm-audit.view-COUNTRY_REGULATORY', {}, { timeout: 5000 });
    expect(screen.getByTestId('perm-permissions.manage-HQ_REGULATORY')).toBeDisabled();
    expect(screen.getByTestId('perm-audit.view-CEO_ADMIN')).toBeDisabled();
    await userEvent.click(box);
    await userEvent.click(screen.getByTestId('save-permissions'));
    await waitFor(() =>
      expect(sent).toEqual({
        grants: [{ action: 'audit.view', role: 'COUNTRY_REGULATORY', allowed: true }],
      }),
    );
  });

  it("n'est pas proposée au siège", async () => {
    loginAs('u-hq');
    renderApp('/admin/permissions');
    expect(await screen.findByTestId('forbidden', {}, { timeout: 5000 })).toBeInTheDocument();
  });
});
