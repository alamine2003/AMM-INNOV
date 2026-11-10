import { useState } from 'react';
import {
  Alert,
  Button,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import RestoreFromTrashIcon from '@mui/icons-material/RestoreFromTrash';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { useRestore, useTrash, type TrashState } from '@/api/hooks/useTrash';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/dates';

const STATES: { value: TrashState; label: string }[] = [
  { value: 'deleted', label: 'À la corbeille' },
  { value: 'restored', label: 'Restaurés' },
  { value: 'all', label: 'Tout' },
];

/**
 * Corbeille (CEO et siège). Rien n'est jamais effacé : ce qui est supprimé dans l'application
 * arrive ici avec tout ce qui partait avec lui, et se restaure à l'identique. La corbeille n'est
 * jamais vidée : une entrée restaurée reste, marquée restaurée.
 */
export default function TrashPage() {
  const [state, setState] = useState<TrashState>('deleted');
  const [page, setPage] = useState(1);
  const trash = useTrash(state, page);
  const restore = useRestore();
  const { enqueueSnackbar } = useSnackbar();
  const rows = trash.data?.results ?? [];
  const pages = trash.data ? Math.max(1, Math.ceil(trash.data.count / Math.max(rows.length, 1))) : 1;

  return (
    <>
      <PageHeader
        title="Corbeille"
        subtitle="Tout ce qui a été supprimé dans AMM GH. Rien n'est effacé : restaurez un élément pour le remettre tel quel."
      />
      <Stack direction="row" alignItems="center" gap={2} sx={{ mb: 2 }}>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={state}
          onChange={(_, value: TrashState | null) => {
            if (value) {
              setState(value);
              setPage(1);
            }
          }}
        >
          {STATES.map((option) => (
            <ToggleButton key={option.value} value={option.value}>
              {option.label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        {trash.data && (
          <Typography variant="body2" color="text.secondary">
            {trash.data.count} élément{trash.data.count > 1 ? 's' : ''}
          </Typography>
        )}
      </Stack>
      {trash.isError && <Alert severity="error">{extractErrorMessage(trash.error)}</Alert>}
      <Paper variant="outlined">
        <Table size="small" data-testid="trash-table">
          <TableHead>
            <TableRow>
              <TableCell>Supprimé le</TableCell>
              <TableCell>Par</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Élément</TableCell>
              <TableCell>Pays</TableCell>
              <TableCell>Motif</TableCell>
              <TableCell align="right">État</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 && !trash.isLoading && (
              <TableRow>
                <TableCell colSpan={7}>
                  <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                    La corbeille est vide.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {rows.map((entry) => (
              <TableRow key={entry.id} hover>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(entry.deleted_at)}</TableCell>
                <TableCell>{entry.deleted_by ?? '—'}</TableCell>
                <TableCell>{entry.kind}</TableCell>
                <TableCell>
                  {entry.label}
                  {entry.rows > 1 && (
                    <Typography component="span" variant="caption" color="text.secondary">
                      {' '}
                      · avec {entry.rows - 1} élément{entry.rows > 2 ? 's' : ''} lié
                      {entry.rows > 2 ? 's' : ''}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>{entry.country || '—'}</TableCell>
                <TableCell>{entry.reason || '—'}</TableCell>
                <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                  {entry.restored_at ? (
                    <Chip
                      size="small"
                      color="success"
                      variant="outlined"
                      label={`Restauré le ${formatDateTime(entry.restored_at)} · ${entry.restored_by ?? ''}`}
                    />
                  ) : (
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<RestoreFromTrashIcon />}
                      disabled={restore.isPending}
                      onClick={() =>
                        restore.mutate(entry.id, {
                          onSuccess: () =>
                            enqueueSnackbar(`« ${entry.label} » restauré.`, { variant: 'success' }),
                          onError: (error) =>
                            enqueueSnackbar(extractErrorMessage(error), { variant: 'error' }),
                        })
                      }
                    >
                      Restaurer
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      {pages > 1 && (
        <Stack direction="row" justifyContent="flex-end" gap={1} sx={{ mt: 1 }}>
          <Button size="small" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Précédent
          </Button>
          <Button size="small" disabled={!trash.data?.next} onClick={() => setPage(page + 1)}>
            Suivant
          </Button>
        </Stack>
      )}
    </>
  );
}
