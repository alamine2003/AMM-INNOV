import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { useDeleteRenewal } from '@/api/hooks/useRenewals';
import type { Amm, Renewal } from '@/api/types';
import { formatDate } from '@/lib/dates';

/**
 * Retour en arrière sur un renouvellement ajouté par erreur. L'AMM est recalculée par le serveur
 * d'après le renouvellement précédent, ou son AMM d'origine ; les scans de la décision annulée
 * sont archivés plutôt que reportés sur une décision qui ne les porte pas.
 */
export function CancelRenewalDialog({
  amm,
  renewal,
  open,
  onClose,
}: {
  amm: Amm;
  renewal: Renewal;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const remove = useDeleteRenewal(amm.id);

  const submit = () =>
    remove.mutate(renewal.id, {
      onSuccess: () => {
        enqueueSnackbar(t('renewals.cancelDone'), { variant: 'success' });
        onClose();
      },
      onError: (error) => enqueueSnackbar(extractErrorMessage(error), { variant: 'error' }),
    });

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="cancel-dialog">
      <DialogTitle>{t('renewals.cancelTitle', { n: renewal.sequence })}</DialogTitle>
      <DialogContent>
        <DialogContentText component="div">
          {t('renewals.cancelConfirm', {
            number: renewal.number || '—',
            start: formatDate(renewal.start_date) || '—',
            end: formatDate(renewal.end_date) || '—',
          })}
        </DialogContentText>
        <Alert severity="warning" sx={{ mt: 2 }}>
          {t('renewals.cancelConsequence')}
        </Alert>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('app.cancel')}</Button>
        <Button
          color="error"
          variant="contained"
          disabled={remove.isPending}
          onClick={submit}
          data-testid="cancel-submit"
        >
          {t('renewals.cancel')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
