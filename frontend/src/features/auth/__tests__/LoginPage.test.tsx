import { afterEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderApp } from '@/test/utils';
import { useAuthStore } from '@/features/auth/authStore';
import { loginRetry } from '@/api/hooks/useAuth';
import { db } from '@/mocks/handlers';
import { server } from '@/mocks/server';

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

  describe('service en cours de démarrage', () => {
    const defaults = { ...loginRetry };
    afterEach(() => Object.assign(loginRetry, defaults));

    async function submit() {
      const user = userEvent.setup();
      renderApp('/login');
      await user.type(await screen.findByLabelText(/adresse e-mail/i), 'siege@amm-innov.test');
      await user.type(screen.getByLabelText(/mot de passe/i), 'Passw0rd!');
      await user.click(screen.getByRole('button', { name: /se connecter/i }));
    }

    it('patiente puis connecte quand le service répond de nouveau', async () => {
      Object.assign(loginRetry, { delayMs: 150, budgetMs: 5000 });
      let calls = 0;
      server.use(
        http.post('/api/v1/auth/login', () => {
          calls += 1;
          return calls < 3 ? new HttpResponse(null, { status: 503 }) : undefined;
        }),
      );
      await submit();
      expect(await screen.findByTestId('login-starting')).toHaveTextContent('Connexion au service en cours');
      expect(screen.queryByTestId('login-error')).toBeNull();
      await waitFor(() => expect(useAuthStore.getState().user?.role).toBe('HQ_REGULATORY'));
      expect(calls).toBe(3);
    });

    it('annonce une indisponibilité, sans message technique, si le service ne revient pas', async () => {
      Object.assign(loginRetry, { delayMs: 20, budgetMs: 200 });
      server.use(http.post('/api/v1/auth/login', () => new HttpResponse(null, { status: 503 })));
      await submit();
      expect(await screen.findByTestId('login-error')).toHaveTextContent(
        'Le service est momentanément indisponible. Veuillez réessayer dans quelques instants.',
      );
      expect(screen.queryByTestId('login-starting')).toBeNull();
    });

    it('ne retente pas un refus : identifiants incorrects affichés tout de suite', async () => {
      let calls = 0;
      server.use(
        http.post('/api/v1/auth/login', () => {
          calls += 1;
          return HttpResponse.json({ detail: 'Identifiants incorrects' }, { status: 401 });
        }),
      );
      await submit();
      expect(await screen.findByTestId('login-error')).toHaveTextContent('Identifiants incorrects');
      expect(calls).toBe(1);
    });
  });
});
