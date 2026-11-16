import { useEffect } from 'react';
import { isRouteErrorResponse, useRouteError } from 'react-router';
import { Alert, Box, Button, CircularProgress, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { reportError } from '@/lib/reportError';
import { isStaleChunkError, reloadForNewVersion } from '@/lib/staleChunks';

/**
 * Erreur pendant l'affichage d'une page : au lieu de l'écran brut de React Router, un message
 * clair. Une nouvelle version déployée pendant que l'onglet était ouvert se recharge seule.
 */
export function RouteError() {
  const { t } = useTranslation();
  const error = useRouteError();
  const stale = isStaleChunkError(error);
  const reloading = stale && typeof window !== 'undefined';

  useEffect(() => {
    if (stale) reloadForNewVersion();
    else reportError(error); // au journal des erreurs (Administration › Erreurs)
  }, [stale, error]);

  if (reloading) {
    return (
      <Stack alignItems="center" gap={2} sx={{ py: 8 }} data-testid="route-error-reloading">
        <CircularProgress />
        <Typography color="text.secondary">{t('common.routeError.reloading')}</Typography>
        <Button variant="outlined" onClick={() => window.location.reload()}>
          {t('common.routeError.reloadNow')}
        </Button>
      </Stack>
    );
  }

  const detail = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : '';
  return (
    <Box sx={{ maxWidth: 640, mx: 'auto', py: 6 }} data-testid="route-error">
      <Alert severity="error" sx={{ mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>
          {t('common.routeError.title')}
        </Typography>
        <Typography variant="body2">{t('common.routeError.body')}</Typography>
        {detail && (
          <Typography variant="caption" component="p" sx={{ mt: 1, fontFamily: 'monospace' }}>
            {detail}
          </Typography>
        )}
      </Alert>
      <Stack direction="row" gap={1}>
        <Button variant="contained" onClick={() => window.location.reload()}>
          {t('common.routeError.reload')}
        </Button>
        <Button href="/">{t('common.routeError.home')}</Button>
      </Stack>
    </Box>
  );
}
