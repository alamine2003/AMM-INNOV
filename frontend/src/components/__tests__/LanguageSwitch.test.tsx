import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { z } from 'zod';
import { db } from '@/mocks/handlers';
import { useAuthStore } from '@/features/auth/authStore';
import i18n, { setLanguage } from '@/lib/i18n';
import { loginAs, renderApp } from '@/test/utils';

describe('Bouton de langue FR / EN', () => {
  it("passe toute l'interface en anglais et l'enregistre sur le compte", async () => {
    loginAs('u-hq');
    renderApp('/');
    expect(await screen.findByRole('link', { name: 'Classeurs' })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('fr');

    await userEvent.click(screen.getAllByTestId('language-en')[0]);

    expect(await screen.findByRole('link', { name: 'Binders' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Classeurs' })).not.toBeInTheDocument();
    expect(document.documentElement.lang).toBe('en');
    expect(localStorage.getItem('amm-gh.language')).toBe('en');
    // Les messages de validation des formulaires suivent.
    expect(z.string().min(1).safeParse('').error?.issues[0].message).toBe('Required field');
    await waitFor(() => expect(db.users.find((u) => u.id === 'u-hq')?.language).toBe('en'));
    expect(useAuthStore.getState().user?.language).toBe('en');

    await userEvent.click(screen.getAllByTestId('language-fr')[0]);
    expect(await screen.findByRole('link', { name: 'Classeurs' })).toBeInTheDocument();
    await waitFor(() => expect(db.users.find((u) => u.id === 'u-hq')?.language).toBe('fr'));
  });

  it('prend la langue du compte à la connexion', async () => {
    db.users.find((u) => u.id === 'u-sn')!.language = 'en';
    loginAs('u-sn');
    renderApp('/');
    expect(await screen.findByRole('link', { name: 'Binders' })).toBeInTheDocument();
    expect(i18n.language).toBe('en');
  });

  it('se choisit dès la page de connexion, puis rejoint le compte', async () => {
    renderApp('/login');
    expect(await screen.findByRole('button', { name: 'Se connecter' })).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('language-en'));
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(i18n.language).toBe('en');

    loginAs('u-ci'); // compte en français : le choix fait à l'instant l'emporte
    await waitFor(() => expect(db.users.find((u) => u.id === 'u-ci')?.language).toBe('en'));
    expect(i18n.language).toBe('en');
  });

  it('retient la langue dans le navigateur pour la prochaine visite', () => {
    setLanguage('en');
    expect(localStorage.getItem('amm-gh.language')).toBe('en');
    expect(i18n.language).toBe('en');
  });
});
