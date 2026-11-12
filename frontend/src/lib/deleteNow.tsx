import { Button } from '@mui/material';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { useRestore } from '@/api/hooks/useTrash';
import { useCan } from '@/features/auth/authStore';

/**
 * Suppressions immédiates, sans question : l'élément part à la corbeille (rien n'est effacé) et
 * un message propose « Annuler » quelques secondes, pour qui peut restaurer. Supprimer deux fois
 * ne montre jamais d'erreur : le serveur répond que c'est déjà fait.
 */
export function useDeletedNotice() {
  const restore = useRestore();
  const canRestore = useCan('trash.restore');
  const { enqueueSnackbar, closeSnackbar } = useSnackbar();
  return (message: string, trashEntry?: string) => {
    const key = enqueueSnackbar(message, {
      variant: 'info',
      autoHideDuration: 10000,
      action:
        trashEntry && canRestore ? (
          <Button
            color="inherit"
            size="small"
            data-testid="undo-delete"
            onClick={() => {
              closeSnackbar(key);
              restore.mutate(trashEntry, {
                onSuccess: () => enqueueSnackbar('Restauré.', { variant: 'success' }),
                onError: (error) => enqueueSnackbar(extractErrorMessage(error), { variant: 'error' }),
              });
            }}
          >
            Annuler
          </Button>
        ) : undefined,
    });
  };
}
