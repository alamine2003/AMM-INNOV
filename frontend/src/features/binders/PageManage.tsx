import { useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from '@mui/material';
import { extractErrorMessage } from '@/api/client';
import { usePageEdits } from '@/api/hooks/useBinders';
import { useRestore } from '@/api/hooks/useTrash';
import { useSnackbar } from 'notistack';
import type { BinderDetail, BinderPage } from '@/api/types';

/** Titre de la page : le nom de la présentation, changé partout dans AMM GH. */
export function RenamePageDialog({
  binder,
  page,
  open,
  onClose,
}: {
  binder: BinderDetail;
  page: BinderPage;
  open: boolean;
  onClose: () => void;
}) {
  const edits = usePageEdits(binder.key, page.amm_id);
  const [name, setName] = useState(page.product_name);
  const save = () =>
    edits.rename.mutate(name.trim(), {
      onSuccess: () => {
        edits.rename.reset();
        onClose();
      },
    });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="rename-page-dialog">
      <DialogTitle>Modifier le titre de la page</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          fullWidth
          label="Nom de la présentation"
          value={name}
          onChange={(e) => setName(e.target.value)}
          sx={{ mt: 1 }}
          slotProps={{ htmlInput: { 'data-testid': 'rename-page-input' } }}
        />
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
          Le nouveau titre s'applique partout dans AMM GH : fiche AMM, classeurs, tableaux de bord, et tous
          les pays qui suivent cette présentation. L'ancien nom reste reconnu par les imports et la
          synchronisation.
        </Typography>
        {edits.rename.isError && (
          <Alert severity="error" sx={{ mt: 1.5 }}>
            {extractErrorMessage(edits.rename.error)}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Annuler</Button>
        <Button
          variant="contained"
          onClick={save}
          disabled={!name.trim() || name.trim() === page.product_name || edits.rename.isPending}
        >
          Renommer
        </Button>
      </DialogActions>
    </Dialog>
  );
}

/**
 * Supprimer la page : immédiat, sans question. La fiche AMM part à la corbeille avec ses pièces
 * (rien n'est effacé) ; « Annuler », juste après, la restaure telle quelle. Un administrateur peut
 * aussi la restaurer plus tard depuis la Corbeille.
 */
export function useDeletePageNow(binder: BinderDetail, page: BinderPage) {
  const edits = usePageEdits(binder.key, page.amm_id);
  const restore = useRestore();
  const { enqueueSnackbar, closeSnackbar } = useSnackbar();
  const run = () =>
    edits.remove.mutate(undefined, {
      onSuccess: ({ trashEntry }) => {
        const key = enqueueSnackbar(`Page « ${page.product_name} » mise à la corbeille.`, {
          variant: 'info',
          autoHideDuration: 10000,
          action: trashEntry ? (
            <Button
              color="inherit"
              size="small"
              data-testid="undo-delete-page"
              onClick={() => {
                closeSnackbar(key);
                restore.mutate(trashEntry, {
                  onSuccess: () => enqueueSnackbar('Page restaurée.', { variant: 'success' }),
                  onError: (error) => enqueueSnackbar(extractErrorMessage(error), { variant: 'error' }),
                });
              }}
            >
              Annuler
            </Button>
          ) : undefined,
        });
      },
      onError: (error) => enqueueSnackbar(extractErrorMessage(error), { variant: 'error' }),
    });
  return { run, pending: edits.remove.isPending };
}
