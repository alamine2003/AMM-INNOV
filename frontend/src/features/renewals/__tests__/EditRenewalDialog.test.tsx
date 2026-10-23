import { describe, expect, it } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { loginAs, renderApp } from '@/test/utils';
import { db } from '@/mocks/handlers';

describe('Correction d’un renouvellement', () => {
  it('corrige le n° et la date de début d’un renouvellement déjà enregistré', async () => {
    const user = userEvent.setup();
    loginAs('u-ceo');
    renderApp('/amms/amm-1?tab=renewals');
    await user.click(await screen.findByTestId('renewal-edit-1', {}, { timeout: 5000 }));
    const dialog = await screen.findByTestId('edit-renewal-dialog');
    const number = dialog.querySelector('input[name="number"]') as HTMLInputElement;
    fireEvent.change(number, { target: { value: 'SN-2024-0999' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Date de début' }), {
      target: { value: '02/03/2024' },
    });
    await user.click(screen.getByTestId('edit-renewal-save'));
    await waitFor(() => expect(screen.queryByTestId('edit-renewal-dialog')).toBeNull());
    const renewal = db.renewals.find((r) => r.amm_id === 'amm-1');
    expect(renewal?.number).toBe('SN-2024-0999');
    expect(renewal?.start_date).toBe('2024-03-02');
  });
});
