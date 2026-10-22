import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { loginAs, renderApp } from '@/test/utils';
import { db } from '@/mocks/handlers';

describe('Correction du classement d’un scan', () => {
  it('range un scan sur une autre période sans changer le fichier', async () => {
    const user = userEvent.setup();
    loginAs('u-ceo');
    renderApp('/amms/amm-1?tab=documents');
    await user.click(await screen.findByTestId('doc-edit-doc-3', {}, { timeout: 5000 }));
    const dialog = await screen.findByTestId('edit-document-dialog');
    await user.click(within(dialog).getByRole('combobox', { name: 'Période' }));
    await user.click(await screen.findByRole('option', { name: /Renouvellement 1/ }));
    await user.click(screen.getByTestId('edit-document-save'));
    await waitFor(() => expect(screen.queryByTestId('edit-document-dialog')).toBeNull());
    expect(db.documents.find((d) => d.id === 'doc-3')?.renewal_id).toBe('amm-1-ren-1');
  });

  it('le siège peut retirer un scan', async () => {
    loginAs('u-hq');
    renderApp('/amms/amm-1?tab=documents');
    expect(await screen.findByTestId('document-doc-3', {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Supprimer|Retirer|Archiver/ }).length).toBeGreaterThan(0);
  });
});
