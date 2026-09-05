import { Fragment, useState } from 'react';
import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useMergeDuplicates, useMergeProduct } from '@/api/hooks/useCatalog';
import type { DuplicateGroup } from '@/api/types';
import { extractErrorMessage } from '@/api/client';

/**
 * Groupes de produits dont le libellé ne diffère que par la ponctuation (`B/100` vs `B100`).
 * Un groupe est en conflit quand deux de ses produits ont une AMM dans le même pays : la fusion
 * garderait une seule des deux AMM, la décision revient à une personne.
 */
export function DuplicatesDialog({
  open,
  onClose,
  groups,
  canMerge,
}: {
  open: boolean;
  onClose: () => void;
  groups: DuplicateGroup[];
  canMerge: boolean;
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const mergeAll = useMergeDuplicates();
  const mergeOne = useMergeProduct();
  const [busyGroup, setBusyGroup] = useState<string | null>(null);
  const clean = groups.filter((g) => !g.conflict).length;

  const keep = async (group: DuplicateGroup, keepId: string) => {
    setBusyGroup(group.key);
    try {
      for (const p of group.products) {
        if (p.id !== keepId) await mergeOne.mutateAsync({ id: p.id, target_id: keepId });
      }
      enqueueSnackbar(t('products.duplicates.merged'), { variant: 'success' });
    } catch (e) {
      enqueueSnackbar(extractErrorMessage(e), { variant: 'error' });
    } finally {
      setBusyGroup(null);
    }
  };

  const mergeClean = () =>
    mergeAll.mutate(false, {
      onSuccess: (r) =>
        enqueueSnackbar(
          t('products.duplicates.mergedAll', { groups: r.merged_groups, products: r.merged_products }),
          { variant: 'success' },
        ),
      onError: (e) => enqueueSnackbar(extractErrorMessage(e), { variant: 'error' }),
    });

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{t('products.duplicates.title', { count: groups.length })}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            {t('products.duplicates.help')}
          </Typography>
          {canMerge && clean > 0 && (
            <Alert
              severity="info"
              action={
                <Button color="inherit" size="small" disabled={mergeAll.isPending} onClick={mergeClean}>
                  {t('products.duplicates.mergeAll', { count: clean })}
                </Button>
              }
            >
              {t('products.duplicates.mergeAllHelp')}
            </Alert>
          )}
          <Table size="small" data-testid="duplicates-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('products.name')}</TableCell>
                <TableCell>{t('products.range')}</TableCell>
                <TableCell align="right">{t('nav.amms')}</TableCell>
                <TableCell>{t('amm.fields.country')}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {groups.map((group) => (
                <Fragment key={group.key}>
                  <TableRow sx={{ bgcolor: 'action.hover' }}>
                    <TableCell colSpan={5}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                          {group.key}
                        </Typography>
                        {group.conflict ? (
                          <Chip
                            size="small"
                            color="warning"
                            label={t('products.duplicates.conflict', {
                              countries: group.conflict_countries.join(', '),
                            })}
                          />
                        ) : (
                          <Chip size="small" color="success" label={t('products.duplicates.noConflict')} />
                        )}
                      </Stack>
                    </TableCell>
                  </TableRow>
                  {group.products.map((p) => (
                    <TableRow key={p.id} data-testid={`duplicate-${p.id}`}>
                      <TableCell>
                        {p.name}
                        {p.id === group.suggested_keep_id && (
                          <Chip size="small" label={t('products.duplicates.suggested')} sx={{ ml: 1 }} />
                        )}
                      </TableCell>
                      <TableCell>{p.range_code ?? '—'}</TableCell>
                      <TableCell align="right">{p.amm_count}</TableCell>
                      <TableCell>{p.countries.join(', ') || '—'}</TableCell>
                      <TableCell align="right">
                        {canMerge && (
                          <Button
                            size="small"
                            disabled={busyGroup !== null}
                            onClick={() => void keep(group, p.id)}
                          >
                            {t('products.duplicates.keep')}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('app.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}
