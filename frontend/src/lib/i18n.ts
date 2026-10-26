import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { z } from 'zod';
import fr from '@/locales/fr.json';

// Messages de validation des formulaires en français (« Trop petit : … » au lieu de « Too small »).
z.config(z.locales.fr());
z.config({
  customError: (issue) =>
    issue.code === 'too_small' && issue.origin === 'string' && Number(issue.minimum) === 1
      ? 'Champ obligatoire'
      : undefined,
});

void i18n.use(initReactI18next).init({
  resources: { fr: { translation: fr } },
  lng: 'fr',
  fallbackLng: 'fr',
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;
