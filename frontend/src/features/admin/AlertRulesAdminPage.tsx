import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  ListItemText,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useAlertRuleMutations, useAlertRules } from '@/api/hooks/useAlerts';
import { useCountries } from '@/api/hooks/useCatalog';
import type { AlertRule, Role } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { SeverityChip } from '@/components/chips';
import { extractErrorMessage } from '@/api/client';

const CODES = ['J-365', 'J-180', 'J-90', 'J-30', 'J0', 'DECISION', 'DOSSIER'];
const ROLES: Role[] = ['COUNTRY_REGULATORY', 'HQ_REGULATORY', 'CEO_ADMIN'];
const CHANNELS = ['in_app', 'email'];

const schema = z.object({
  code: z.string().min(1),
  country: z.string(),
  offset_days: z.coerce.number().int().min(0),
  severity: z.enum(['INFO', 'WARNING', 'CRITICAL']),
  roles: z.array(z.string()),
  channels: z.array(z.string()),
  only_if_not_filed: z.boolean(),
  is_active: z.boolean(),
});
type Values = z.infer<typeof schema>;

function RuleDialog({ open, onClose, rule }: { open: boolean; onClose: () => void; rule: AlertRule | null }) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const countries = useCountries();
  const { create, update } = useAlertRuleMutations();
  const { control, register, handleSubmit, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: rule
      ? { ...rule, country: rule.country ?? '' }
      : {
          code: 'J-180',
          country: '',
          offset_days: 180,
          severity: 'WARNING',
          roles: ['COUNTRY_REGULATORY'],
          channels: ['in_app'],
          only_if_not_filed: true,
          is_active: true,
        },
  });
  const submit = (values: Values) => {
    const payload = { ...values, country: values.country || null, roles: values.roles as Role[] };
    const m = rule ? update.mutateAsync({ id: rule.id, ...payload }) : create.mutateAsync(payload);
    void m
      .then(() => {
        enqueueSnackbar(t('admin.rules.saved'), { variant: 'success' });
        onClose();
      })
      .catch(() => undefined);
  };
  const error = create.error ?? update.error;
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{rule ? t('app.edit') : t('admin.rules.create')}</DialogTitle>
      <form onSubmit={handleSubmit(submit)} noValidate>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction="row" spacing={2}>
              <Controller
                control={control}
                name="code"
                render={({ field }) => (
                  <TextField select fullWidth label={t('admin.rules.code')} {...field}>
                    {CODES.map((c) => (
                      <MenuItem key={c} value={c}>
                        {c}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              />
              <Controller
                control={control}
                name="country"
                render={({ field }) => (
                  <TextField select fullWidth label={t('admin.rules.country')} {...field}>
                    <MenuItem value="">{t('admin.rules.global')}</MenuItem>
                    {(countries.data ?? []).map((c) => (
                      <MenuItem key={c.id} value={c.id}>
                        {c.name}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              />
            </Stack>
            <Stack direction="row" spacing={2}>
              <TextField
                label={t('admin.rules.offset')}
                type="number"
                fullWidth
                {...register('offset_days')}
                error={!!formState.errors.offset_days}
              />
              <Controller
                control={control}
                name="severity"
                render={({ field }) => (
                  <TextField select fullWidth label={t('admin.rules.severity')} {...field}>
                    {(['INFO', 'WARNING', 'CRITICAL'] as const).map((s) => (
                      <MenuItem key={s} value={s}>
                        {t(`severity.${s}`)}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              />
            </Stack>
            <Controller
              control={control}
              name="roles"
              render={({ field }) => (
                <TextField
                  select
                  label={t('admin.rules.roles')}
                  slotProps={{
                    select: {
                      multiple: true,
                      renderValue: (v) => (v as string[]).map((r) => t(`roles.${r}`)).join(', '),
                    },
                  }}
                  {...field}
                >
                  {ROLES.map((r) => (
                    <MenuItem key={r} value={r}>
                      <Checkbox checked={field.value.includes(r)} />
                      <ListItemText primary={t(`roles.${r}`)} />
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
            <Controller
              control={control}
              name="channels"
              render={({ field }) => (
                <TextField
                  select
                  label={t('admin.rules.channels')}
                  slotProps={{ select: { multiple: true, renderValue: (v) => (v as string[]).join(', ') } }}
                  {...field}
                >
                  {CHANNELS.map((c) => (
                    <MenuItem key={c} value={c}>
                      <Checkbox checked={field.value.includes(c)} />
                      <ListItemText primary={c} />
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
            <Controller
              control={control}
              name="only_if_not_filed"
              render={({ field }) => (
                <FormControlLabel
                  control={
                    <Switch checked={field.value} onChange={(e) => field.onChange(e.target.checked)} />
                  }
                  label={t('admin.rules.onlyIfNotFiled')}
                />
              )}
            />
            <Controller
              control={control}
              name="is_active"
              render={({ field }) => (
                <FormControlLabel
                  control={
                    <Switch checked={field.value} onChange={(e) => field.onChange(e.target.checked)} />
                  }
                  label={t('admin.rules.active')}
                />
              )}
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

export default function AlertRulesAdminPage() {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const rules = useAlertRules();
  const countries = useCountries();
  const { remove } = useAlertRuleMutations();
  const [dialog, setDialog] = useState<{ open: boolean; rule: AlertRule | null }>({
    open: false,
    rule: null,
  });
  const [deleting, setDeleting] = useState<AlertRule | null>(null);
  const columns: GridColDef<AlertRule>[] = [
    { field: 'code', headerName: t('admin.rules.code'), width: 110 },
    {
      field: 'country',
      headerName: t('admin.rules.country'),
      width: 150,
      valueGetter: (_v, row) =>
        row.country
          ? (countries.data?.find((c) => c.id === row.country || c.iso2 === row.country)?.name ?? row.country)
          : t('admin.rules.global'),
    },
    { field: 'offset_days', headerName: t('admin.rules.offset'), width: 130 },
    {
      field: 'severity',
      headerName: t('admin.rules.severity'),
      width: 130,
      renderCell: (p) => <SeverityChip value={p.row.severity} />,
    },
    {
      field: 'roles',
      headerName: t('admin.rules.roles'),
      flex: 1,
      minWidth: 220,
      valueGetter: (_v, row) => row.roles.map((r) => t(`roles.${r}`)).join(', '),
    },
    {
      field: 'channels',
      headerName: t('admin.rules.channels'),
      width: 140,
      valueGetter: (_v, row) => row.channels.join(', '),
    },
    {
      field: 'only_if_not_filed',
      headerName: t('admin.rules.onlyIfNotFiled'),
      width: 170,
      renderCell: (p) => (p.row.only_if_not_filed ? t('app.yes') : t('app.no')),
    },
    {
      field: 'is_active',
      headerName: t('admin.rules.active'),
      width: 90,
      renderCell: (p) => (
        <Chip
          size="small"
          label={p.row.is_active ? t('app.yes') : t('app.no')}
          color={p.row.is_active ? 'success' : 'default'}
        />
      ),
    },
    {
      field: 'actions',
      headerName: '',
      width: 100,
      sortable: false,
      renderCell: (p) => (
        <>
          <IconButton
            size="small"
            onClick={() => setDialog({ open: true, rule: p.row })}
            aria-label={t('app.edit')}
          >
            <EditIcon fontSize="small" />
          </IconButton>
          <IconButton
            size="small"
            color="error"
            onClick={() => setDeleting(p.row)}
            aria-label={t('app.delete')}
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </>
      ),
    },
  ];
  return (
    <Box>
      <PageHeader
        title={t('admin.rules.title')}
        actions={
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setDialog({ open: true, rule: null })}
          >
            {t('admin.rules.create')}
          </Button>
        }
      />
      <Paper variant="outlined" sx={{ height: 'calc(100vh - 240px)', minHeight: 400 }}>
        <DataGrid
          rows={rules.data ?? []}
          columns={columns}
          loading={rules.isPending}
          density="compact"
          disableRowSelectionOnClick
          sx={{ border: 0 }}
        />
      </Paper>
      {dialog.open && (
        <RuleDialog open onClose={() => setDialog({ open: false, rule: null })} rule={dialog.rule} />
      )}
      <ConfirmDialog
        open={!!deleting}
        title={t('app.confirmDelete')}
        text={deleting ? `${deleting.code}` : undefined}
        onClose={() => setDeleting(null)}
        loading={remove.isPending}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => {
              enqueueSnackbar(t('admin.rules.deleted'), { variant: 'success' });
              setDeleting(null);
            },
            onError: (e) => enqueueSnackbar(extractErrorMessage(e), { variant: 'error' }),
          })
        }
      />
    </Box>
  );
}
