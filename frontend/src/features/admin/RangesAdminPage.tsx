import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Stack,
  TextField,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useRangeMutations, useRanges } from '@/api/hooks/useCatalog';
import type { ProductRange } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { extractErrorMessage } from '@/api/client';
import { isAdmin, useAuthStore } from '@/features/auth/authStore';

const schema = z.object({ code: z.string().min(1).toUpperCase(), label: z.string().min(1) });
type Values = z.infer<typeof schema>;

function RangeDialog({
  open,
  onClose,
  range,
}: {
  open: boolean;
  onClose: () => void;
  range: ProductRange | null;
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const { create, update } = useRangeMutations();
  const { register, handleSubmit, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: range ?? { code: '', label: '' },
  });
  const submit = (values: Values) => {
    const m = range ? update.mutateAsync({ id: range.id, ...values }) : create.mutateAsync(values);
    void m
      .then(() => {
        enqueueSnackbar(t('admin.ranges.saved'), { variant: 'success' });
        onClose();
      })
      .catch(() => undefined);
  };
  const error = create.error ?? update.error;
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{range ? t('app.edit') : t('admin.ranges.create')}</DialogTitle>
      <form onSubmit={handleSubmit(submit)} noValidate>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label={t('admin.ranges.code')} {...register('code')} error={!!formState.errors.code} />
            <TextField
              label={t('admin.ranges.label')}
              {...register('label')}
              error={!!formState.errors.label}
            />
            {error && <Alert severity="error">{extractErrorMessage(error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('app.cancel')}</Button>
          <Button type="submit" variant="contained" disabled={create.isPending || update.isPending}>
            {t('app.save')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

export default function RangesAdminPage() {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const user = useAuthStore((s) => s.user);
  const ranges = useRanges();
  const { remove } = useRangeMutations();
  const [dialog, setDialog] = useState<{ open: boolean; range: ProductRange | null }>({
    open: false,
    range: null,
  });
  const [deleting, setDeleting] = useState<ProductRange | null>(null);
  const columns: GridColDef<ProductRange>[] = [
    { field: 'code', headerName: t('admin.ranges.code'), width: 160 },
    { field: 'label', headerName: t('admin.ranges.label'), flex: 1, minWidth: 200 },
    {
      field: 'actions',
      headerName: '',
      width: 100,
      sortable: false,
      renderCell: (p) => (
        <>
          <IconButton
            size="small"
            onClick={() => setDialog({ open: true, range: p.row })}
            aria-label={t('app.edit')}
          >
            <EditIcon fontSize="small" />
          </IconButton>
          {isAdmin(user) && (
            <IconButton
              size="small"
              color="error"
              onClick={() => setDeleting(p.row)}
              aria-label={t('app.delete')}
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          )}
        </>
      ),
    },
  ];
  return (
    <Box>
      <PageHeader
        title={t('admin.ranges.title')}
        actions={
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setDialog({ open: true, range: null })}
          >
            {t('admin.ranges.create')}
          </Button>
        }
      />
      <Paper variant="outlined" sx={{ height: 400 }}>
        <DataGrid
          rows={ranges.data ?? []}
          columns={columns}
          loading={ranges.isPending}
          density="compact"
          disableRowSelectionOnClick
          sx={{ border: 0 }}
        />
      </Paper>
      {dialog.open && (
        <RangeDialog open onClose={() => setDialog({ open: false, range: null })} range={dialog.range} />
      )}
      <ConfirmDialog
        open={!!deleting}
        title={t('app.confirmDelete')}
        text={deleting?.label}
        onClose={() => setDeleting(null)}
        loading={remove.isPending}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => setDeleting(null),
            onError: (e) => enqueueSnackbar(extractErrorMessage(e), { variant: 'error' }),
          })
        }
      />
    </Box>
  );
}
