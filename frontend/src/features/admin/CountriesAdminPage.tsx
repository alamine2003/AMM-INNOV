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
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useCountries, useCountryMutations } from '@/api/hooks/useCatalog';
import type { Country } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { extractErrorMessage } from '@/api/client';

const schema = z.object({
  iso2: z.string().length(2).toUpperCase(),
  name: z.string().min(1),
  authority: z.string(),
  validity_years: z.coerce.number().int().min(1).max(20),
  filing_lead_months: z.coerce.number().int().min(0).max(36),
  timezone: z.string().min(1),
});
type Values = z.infer<typeof schema>;

function CountryDialog({
  open,
  onClose,
  country,
}: {
  open: boolean;
  onClose: () => void;
  country: Country | null;
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const { create, update } = useCountryMutations();
  const { register, handleSubmit, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: country ?? {
      iso2: '',
      name: '',
      authority: '',
      validity_years: 5,
      filing_lead_months: 6,
      timezone: 'Africa/Dakar',
    },
  });
  const submit = (values: Values) => {
    const m = country ? update.mutateAsync({ id: country.id, ...values }) : create.mutateAsync(values);
    void m
      .then(() => {
        enqueueSnackbar(t('admin.countries.saved'), { variant: 'success' });
        onClose();
      })
      .catch(() => undefined);
  };
  const error = create.error ?? update.error;
  const err = (k: keyof Values) => ({
    error: !!formState.errors[k],
    helperText: formState.errors[k]?.message,
  });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{country ? t('app.edit') : t('admin.countries.create')}</DialogTitle>
      <form onSubmit={handleSubmit(submit)} noValidate>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction="row" spacing={2}>
              <TextField
                label={t('admin.countries.iso2')}
                sx={{ width: 120 }}
                disabled={!!country}
                {...register('iso2')}
                {...err('iso2')}
              />
              <TextField label={t('admin.countries.name')} fullWidth {...register('name')} {...err('name')} />
            </Stack>
            <TextField label={t('admin.countries.authority')} {...register('authority')} />
            <Stack direction="row" spacing={2}>
              <TextField
                label={t('admin.countries.validity')}
                type="number"
                fullWidth
                {...register('validity_years')}
                {...err('validity_years')}
              />
              <TextField
                label={t('admin.countries.lead')}
                type="number"
                fullWidth
                {...register('filing_lead_months')}
                {...err('filing_lead_months')}
              />
            </Stack>
            <TextField label={t('admin.countries.timezone')} {...register('timezone')} {...err('timezone')} />
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

export default function CountriesAdminPage() {
  const { t } = useTranslation();
  const countries = useCountries();
  const [dialog, setDialog] = useState<{ open: boolean; country: Country | null }>({
    open: false,
    country: null,
  });
  const columns: GridColDef<Country>[] = [
    { field: 'iso2', headerName: t('admin.countries.iso2'), width: 90 },
    { field: 'name', headerName: t('admin.countries.name'), flex: 1, minWidth: 180 },
    { field: 'authority', headerName: t('admin.countries.authority'), flex: 1, minWidth: 160 },
    { field: 'validity_years', headerName: t('admin.countries.validity'), width: 130 },
    { field: 'filing_lead_months', headerName: t('admin.countries.lead'), width: 170 },
    { field: 'timezone', headerName: t('admin.countries.timezone'), width: 160 },
    {
      field: 'actions',
      headerName: '',
      width: 70,
      sortable: false,
      renderCell: (p) => (
        <IconButton
          size="small"
          onClick={() => setDialog({ open: true, country: p.row })}
          aria-label={t('app.edit')}
        >
          <EditIcon fontSize="small" />
        </IconButton>
      ),
    },
  ];
  return (
    <Box>
      <PageHeader
        title={t('admin.countries.title')}
        actions={
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setDialog({ open: true, country: null })}
          >
            {t('admin.countries.create')}
          </Button>
        }
      />
      <Paper variant="outlined" sx={{ height: 'calc(100vh - 240px)', minHeight: 400 }}>
        <DataGrid
          rows={countries.data ?? []}
          columns={columns}
          loading={countries.isPending}
          density="compact"
          disableRowSelectionOnClick
          sx={{ border: 0 }}
        />
      </Paper>
      {dialog.open && (
        <CountryDialog
          open
          onClose={() => setDialog({ open: false, country: null })}
          country={dialog.country}
        />
      )}
    </Box>
  );
}
