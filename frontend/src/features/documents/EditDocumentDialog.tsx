import { useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { useUpdateDocument, type DocumentEdit } from '@/api/hooks/useDocuments';
import type { Amm, AmmDocument, DocumentKind, Renewal } from '@/api/types';
import { formatDate } from '@/lib/dates';

const KINDS: DocumentKind[] = ['AMM', 'RECEPISSE', 'COURRIER', 'AUTRE'];
const ORIGIN = 'origine';

/**
 * Corrige le classement d'un scan mal rangé : son type, sa période (AMM d'origine ou un
 * renouvellement), sa date et son titre. Le fichier ne change pas (« Remplacer » pour cela).
 */
export function EditDocumentDialog({
  amm,
  document,
  renewals,
  open,
  onClose,
}: {
  amm: Amm;
  document: AmmDocument;
  renewals: Renewal[];
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const update = useUpdateDocument(amm.id);
  const [kind, setKind] = useState<DocumentKind>(document.kind);
  const [period, setPeriod] = useState<string>(document.renewal_id ?? ORIGIN);
  const [date, setDate] = useState(document.document_date);
  const [title, setTitle] = useState(document.title ?? '');

  const payload: DocumentEdit = {};
  if (kind !== document.kind) payload.kind = kind;
  if (period !== (document.renewal_id ?? ORIGIN)) payload.renewal = period === ORIGIN ? null : period;
  if (date && date !== document.document_date) payload.document_date = date;
  if (title !== (document.title ?? '')) payload.title = title;
  const dirty = Object.keys(payload).length > 0;

  const submit = () =>
    update.mutate(
      { documentId: document.id, ...payload },
      {
        onSuccess: () => {
          enqueueSnackbar('Classement du scan corrigé', { variant: 'success' });
          onClose();
        },
      },
    );

  const sorted = [...renewals].sort((a, b) => b.sequence - a.sequence);
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="edit-document-dialog">
      <DialogTitle>Corriger le classement du scan</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Le fichier ne change pas. L'état du dossier, la fiche et les classeurs sont mis à jour.
        </Typography>
        <Stack spacing={2}>
          <TextField
            select
            label="Période"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            data-testid="edit-document-period"
          >
            {sorted.map((r) => (
              <MenuItem key={r.id} value={r.id}>
                Renouvellement {r.sequence}
                {r.number ? ` — n° ${r.number}` : ''}
                {r.start_date ? ` — début ${formatDate(r.start_date)}` : ''}
              </MenuItem>
            ))}
            <MenuItem value={ORIGIN}>
              AMM d'origine{amm.original_number ? ` — n° ${amm.original_number}` : ''}
              {amm.original_start_date ? ` — ${formatDate(amm.original_start_date)}` : ''}
            </MenuItem>
          </TextField>
          <TextField
            select
            label="Type"
            value={kind}
            onChange={(e) => setKind(e.target.value as DocumentKind)}
          >
            {KINDS.map((k) => (
              <MenuItem key={k} value={k}>
                {t(`documentKind.${k}`)}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            type="date"
            label="Date du document"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
        </Stack>
        {update.isError && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {extractErrorMessage(update.error)}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Annuler</Button>
        <Button
          variant="contained"
          onClick={submit}
          disabled={!dirty || update.isPending}
          data-testid="edit-document-save"
        >
          Enregistrer
        </Button>
      </DialogActions>
    </Dialog>
  );
}
