import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderApp } from '@/test/utils';
import { useAuthStore } from '@/features/auth/authStore';
import { db } from '@/mocks/handlers';

describe('LoginPage', () => {
  it('connecte l’utilisateur et redirige vers le dashboard', async () => {
    const user = userEvent.setup();
    renderApp('/login');
    await user.type(await screen.findByLabelText(/adresse e-mail/i), 'siege@amm-innov.test');
    await user.type(screen.getByLabelText(/mot de passe/i), 'Passw0rd!');
    await user.click(screen.getByRole('button', { name: /se connecter/i }));
    await waitFor(() => expect(useAuthStore.getState().user?.role).toBe('HQ_REGULATORY'));
    expect(db.session).toBe('u-hq'); // cookie de session posé par l'API, jamais dans localStorage
    expect(localStorage.getItem('amm.refresh')).toBeNull();
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
