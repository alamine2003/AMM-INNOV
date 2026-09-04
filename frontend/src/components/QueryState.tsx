import { Alert, Box, Button, CircularProgress, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { extractErrorMessage } from '@/api/client';

export function LoadingBlock({ minHeight = 160 }: { minHeight?: number }) {
  const { t } = useTranslation();
  return (
    <Box
      sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight, gap: 2 }}
      role="status"
    >
      <CircularProgress size={28} />
      <Typography color="text.secondary">{t('app.loading')}</Typography>
    </Box>
  );
}

export function ErrorBlock({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <Alert
      severity="error"
      action={
        onRetry ? (
          <Button color="inherit" size="small" onClick={onRetry}>
            {t('app.retry')}
          </Button>
        ) : undefined
      }
    >
      {extractErrorMessage(error, t('app.error'))}
    </Alert>
  );
}

export function EmptyBlock({ text }: { text?: string }) {
  const { t } = useTranslation();
  return (
    <Box sx={{ py: 4, textAlign: 'center' }}>
      <Typography color="text.secondary">{text ?? t('app.noData')}</Typography>
    </Box>
  );
}
