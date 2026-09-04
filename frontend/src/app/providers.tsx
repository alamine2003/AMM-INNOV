import type { ReactNode } from 'react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SnackbarProvider } from 'notistack';
import { theme } from './theme';

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
      mutations: { retry: 0 },
    },
  });
}

export function AppProviders({ children, queryClient }: { children: ReactNode; queryClient?: QueryClient }) {
  const client = queryClient ?? defaultClient;
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <SnackbarProvider
          maxSnack={4}
          autoHideDuration={4000}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        >
          {children}
        </SnackbarProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

const defaultClient = createQueryClient();
