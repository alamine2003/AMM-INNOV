import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { loginAs, renderApp } from '@/test/utils';

describe('Cloche de notifications', () => {
  it('affiche le compteur de non lues et la liste', async () => {
    const user = userEvent.setup();
    loginAs('u-hq');
    renderApp('/');
    const badge = await screen.findByTestId('notification-badge', {}, { timeout: 5000 });
    await waitFor(() => expect(within(badge).getByText('3')).toBeInTheDocument());
    await user.click(screen.getByTestId('notification-bell'));
    expect(await screen.findByText(/Alerte J-90/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /tout marquer comme lu/i }));
    // MUI conserve l'ancien contenu pendant la transition de sortie : le badge devient invisible.
    await waitFor(() => expect(badge.querySelector('.MuiBadge-badge')).toHaveClass('MuiBadge-invisible'));
  });
});
