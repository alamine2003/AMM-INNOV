import { createTheme, type ThemeOptions } from '@mui/material/styles';
import { enUS as coreEnUS, frFR as coreFrFR } from '@mui/material/locale';
import { enUS as gridEnUS, frFR as gridFrFR } from '@mui/x-data-grid/locales';
import type { Language } from '@/lib/i18n';

const options: ThemeOptions = {
  palette: {
    mode: 'light',
    // Bleu du logo Generic Healthcare.
    primary: { main: '#204093', dark: '#152b66', light: '#4a66b3' },
    secondary: { main: '#00897b' },
    background: { default: '#f4f6f9', paper: '#ffffff' },
    success: { main: '#2e7d32' },
    warning: { main: '#ef6c00' },
    error: { main: '#c62828' },
    info: { main: '#1565c0' },
  },
  typography: {
    fontFamily: '"Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    h4: { fontWeight: 700 },
    h5: { fontWeight: 700 },
    h6: { fontWeight: 600 },
    subtitle2: { fontWeight: 600 },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { textTransform: 'none', fontWeight: 600 } },
    },
    MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
    MuiTableCell: { styleOverrides: { head: { fontWeight: 700, backgroundColor: '#eef2f6' } } },
  },
};

/** Les textes propres à MUI (pagination, tableaux, « Aucune ligne ») suivent la langue. */
const themes: Record<Language, ReturnType<typeof createTheme>> = {
  fr: createTheme(options, gridFrFR, coreFrFR),
  en: createTheme(options, gridEnUS, coreEnUS),
};

export const themeFor = (language: Language) => themes[language];
export const theme = themes.fr;
