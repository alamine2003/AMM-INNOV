import { createTheme } from '@mui/material/styles';
import { frFR as coreFrFR } from '@mui/material/locale';
import { frFR as gridFrFR } from '@mui/x-data-grid/locales';

export const theme = createTheme(
  {
    palette: {
      mode: 'light',
      primary: { main: '#0f5c8c', dark: '#083d5e', light: '#3f83b0' },
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
  },
  gridFrFR,
  coreFrFR,
);
