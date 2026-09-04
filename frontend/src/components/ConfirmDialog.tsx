import { Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle } from '@mui/material';
import { useTranslation } from 'react-i18next';

export function ConfirmDialog({
  open,
  title,
  text,
  onClose,
  onConfirm,
  loading,
  confirmColor = 'error',
}: {
  open: boolean;
  title: string;
  text?: string;
  onClose: () => void;
  onConfirm: () => void;
  loading?: boolean;
  confirmColor?: 'error' | 'primary';
}) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      {text && (
        <DialogContent>
          <DialogContentText>{text}</DialogContentText>
        </DialogContent>
      )}
      <DialogActions>
        <Button onClick={onClose}>{t('app.cancel')}</Button>
        <Button onClick={onConfirm} color={confirmColor} variant="contained" disabled={loading}>
          {t('app.confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
