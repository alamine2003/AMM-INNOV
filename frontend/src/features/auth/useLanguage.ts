import { useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '@/api/client';
import type { User } from '@/api/types';
import { currentLanguage, isLanguage, setLanguage, type Language } from '@/lib/i18n';
import { useAuthStore } from './authStore';

// Langue choisie sur la page de connexion, avant d'avoir un compte sous la main : elle est
// enregistrée sur le compte dès la connexion, au lieu d'être écrasée par l'ancienne.
let chosenBeforeLogin: Language | null = null;

function useSaveLanguage() {
  const setUser = useAuthStore((s) => s.setUser);
  return useMutation({
    mutationFn: async (language: Language) => (await api.patch<User>('/me', { language })).data,
    onSuccess: (updated) => setUser(updated),
  });
}

/**
 * Langue de l'interface, pour l'afficher et la changer (bouton FR / EN). Elle est gardée sur le
 * compte : l'utilisateur la retrouve sur tout appareil. `choose` l'applique tout de suite, puis
 * l'enregistre ; si l'enregistrement échoue, elle vaut quand même pour cette visite.
 */
export function useLanguage() {
  const { i18n } = useTranslation();
  const { mutate } = useSaveLanguage();
  const language: Language = isLanguage(i18n.language) ? i18n.language : currentLanguage();
  const choose = (next: Language) => {
    setLanguage(next);
    if (useAuthStore.getState().user) mutate(next);
    else chosenBeforeLogin = next;
  };
  return { language, choose };
}

/**
 * À la connexion, l'interface prend la langue du compte, sauf si l'utilisateur vient d'en
 * choisir une autre sur la page de connexion : c'est alors le compte qui est mis à jour.
 * Appelé une seule fois, à la racine de l'application.
 */
export function useAccountLanguage() {
  const userId = useAuthStore((s) => s.user?.id);
  const accountLanguage = useAuthStore((s) => s.user?.language);
  const { mutate } = useSaveLanguage();
  useEffect(() => {
    if (!userId) return;
    const chosen = chosenBeforeLogin;
    chosenBeforeLogin = null;
    if (chosen && chosen !== accountLanguage) mutate(chosen);
    else if (isLanguage(accountLanguage)) setLanguage(accountLanguage);
  }, [userId, accountLanguage, mutate]);
}
