import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { loginAs, renderApp } from '@/test/utils';

describe('Synchronisation AMM GHPL', () => {
  it('montre le dernier passage, ce qui demande une action, et relance à la demande', async () => {
    const user = userEvent.setup();
    loginAs('u-ceo');
    renderApp('/admin/imports');
    const card = await screen.findByTestId('ghpl-sync-card');
    expect(within(card).getByTestId('ghpl-sync-status')).toHaveTextContent('Synchronisé');
    expect(within(card).getByText('9 scans ajoutés')).toBeInTheDocument();
    expect(within(card).getByText('2 reclassés')).toBeInTheDocument();
    expect(within(card).getByText(/document Word : à enregistrer en PDF/)).toBeInTheDocument();
    await user.click(within(card).getByTestId('ghpl-files-chip-SKIPPED'));
    expect(await within(card).findByTestId('ghpl-files-SKIPPED')).toHaveTextContent('lettre.docx');
    await user.click(within(card).getByTestId('ghpl-sync-run'));
    await waitFor(
      () => expect(within(card).getByTestId('ghpl-sync-status')).toHaveTextContent('Déjà à jour'),
      {
        timeout: 5000,
      },
    );
  });
});
