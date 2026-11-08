import { useState } from 'react';
import {
  Alert,
  Autocomplete,
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
import type { BinderDetail, BinderPage } from '@/api/types';

/** Nombre de pièces rangées sur la page (décisions et autres pièces, toutes périodes). */
export function pagePieces(page: BinderPage): number {
  return page.chronology.reduce(
    (total, entry) => total + (entry.decisions?.length ?? 0) + (entry.others?.length ?? 0),
    0,
  );
}

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
 * Supprimer la page : la fiche AMM disparaît de toute l'application. Ses pièces ne sont jamais
 * perdues : une autre fiche du pays les reprend (une page sans pièce se supprime directement).
 */
export function DeletePageDialog({
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
  const pieces = pagePieces(page);
  const others = binder.sections
    .flatMap((section) => section.pages)
    .filter((other) => other.amm_id !== page.amm_id);
  const [target, setTarget] = useState<BinderPage | null>(null);
  const remove = () =>
    edits.remove.mutate(target?.amm_id ?? null, {
      onSuccess: () => {
        edits.remove.reset();
        onClose();
      },
    });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="delete-page-dialog">
      <DialogTitle>Supprimer la page « {page.product_name} »</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 1.5 }}>
          La fiche AMM de cette présentation disparaît de toute l'application ({binder.country_name}) :
          classeurs, fiche, alertes, rappels, tableaux de bord. Les imports et la synchronisation ne la
          recréeront pas ; « Ajouter une page » la fait revenir.
        </Typography>
        {pieces > 0 ? (
          <>
            <Typography variant="body2" sx={{ mb: 1 }}>
              Elle porte {pieces} pièce{pieces > 1 ? 's' : ''} (scans, récépissés…) : aucune n'est supprimée.
              Choisissez la fiche qui les reprend, par exemple le vrai dossier de cette présentation.
            </Typography>
            <Autocomplete
              options={others}
              value={target}
              onChange={(_, value) => setTarget(value)}
              getOptionLabel={(option) => `p. ${option.page} · ${option.product_name}`}
              isOptionEqualToValue={(option, value) => option.amm_id === value.amm_id}
              renderInput={(params) => <TextField {...params} label="Fiche qui reprend les pièces" />}
              data-testid="delete-page-target"
            />
          </>
        ) : (
          <Typography variant="body2" color="text.secondary">
            Aucune pièce n'est rangée sur cette page.
          </Typography>
        )}
        {edits.remove.isError && (
          <Alert severity="error" sx={{ mt: 1.5 }}>
            {extractErrorMessage(edits.remove.error)}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Annuler</Button>
        <Button
          variant="contained"
          color="error"
          onClick={remove}
          disabled={(pieces > 0 && !target) || edits.remove.isPending}
          data-testid="delete-page-confirm"
        >
          Supprimer la page
        </Button>
      </DialogActions>
    </Dialog>
  );
}
