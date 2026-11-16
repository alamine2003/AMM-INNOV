import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { z } from 'zod';
import en from '@/locales/en.json';
import fr from '@/locales/fr.json';

/** Langues de l'interface. Le français est la langue par défaut et celle de repli. */
export type Language = 'fr' | 'en';
export const LANGUAGES: readonly Language[] = ['fr', 'en'];
export const isLanguage = (value: unknown): value is Language => value === 'fr' || value === 'en';

// Avant la connexion (page de connexion, session expirée), la langue vient de ce navigateur ;
// une fois connecté, elle vient du compte (`user.language`, voir `useLanguage`).
const STORAGE_KEY = 'amm-gh.language';

function storedLanguage(): Language | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return isLanguage(value) ? value : null;
  } catch {
    return null; // navigation privée, stockage bloqué : on reste sur le français
  }
}

/** Ce qui suit la langue hors des textes : messages de validation et attribut `lang` de la page. */
function applyLanguage(language: string) {
  // « Trop petit : … » / « Too small: … » selon la langue, et « Champ obligatoire » pour un
  // champ texte laissé vide.
  z.config(language === 'en' ? z.locales.en() : z.locales.fr());
  z.config({
    customError: (issue) =>
      issue.code === 'too_small' && issue.origin === 'string' && Number(issue.minimum) === 1
        ? i18n.t('app.required')
        : undefined,
  });
  if (typeof document !== 'undefined') document.documentElement.lang = language;
}

void i18n.use(initReactI18next).init({
  resources: { fr: { translation: fr }, en: { translation: en } },
  lng: storedLanguage() ?? 'fr',
  fallbackLng: 'fr',
  interpolation: { escapeValue: false },
  returnNull: false,
});
applyLanguage(i18n.language);
i18n.on('languageChanged', applyLanguage);

/** Langue affichée en ce moment. */
export const currentLanguage = (): Language => (isLanguage(i18n.language) ? i18n.language : 'fr');

/** Change la langue de l'interface et la retient dans ce navigateur. */
export function setLanguage(language: Language) {
  try {
    window.localStorage.setItem(STORAGE_KEY, language);
  } catch {
    /* stockage bloqué : la langue vaut pour cette visite */
  }
  if (i18n.language !== language) void i18n.changeLanguage(language);
}

export default i18n;
