import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderApp } from '@/test/utils';
import { useAuthStore } from '@/features/auth/authStore';

describe('LoginPage', () => {
  it('connecte l’utilisateur et redirige vers le dashboard', async () => {
    const user = userEvent.setup();
    renderApp('/login');
    await user.type(await screen.findByLabelText(/adresse e-mail/i), 'siege@amm-innov.test');
    await user.type(screen.getByLabelText(/mot de passe/i), 'Passw0rd!');
    await user.click(screen.getByRole('button', { name: /se connecter/i }));
    await waitFor(() => expect(useAuthStore.getState().user?.role).toBe('HQ_REGULATORY'));
    expect(localStorage.getItem('amm.refresh')).toBe('mock-refresh-u-hq');
    expect(
      await screen.findByRole('heading', { name: 'Dashboard Afrique' }, { timeout: 5000 }),
    ).toBeInTheDocument();
  });

  it('affiche une erreur en cas d’identifiants incorrects', async () => {
    const user = userEvent.setup();
    renderApp('/login');
    await user.type(await screen.findByLabelText(/adresse e-mail/i), 'siege@amm-innov.test');
    await user.type(screen.getByLabelText(/mot de passe/i), 'mauvais');
    await user.click(screen.getByRole('button', { name: /se connecter/i }));
    expect(await screen.findByTestId('login-error')).toHaveTextContent('Identifiants incorrects');
    expect(useAuthStore.getState().user).toBeNull();
  });
});
