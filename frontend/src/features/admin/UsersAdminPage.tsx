import { useState } from 'react';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
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
import { Controller, useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useUserMutations, useUsers } from '@/api/hooks/useUsers';
import { useCountries } from '@/api/hooks/useCatalog';
import type { Role, User } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { extractErrorMessage } from '@/api/client';
import { isAdmin, useAuthStore } from '@/features/auth/authStore';

const schema = z.object({
  email: z.string().email(),
  first_name: z.string().min(1),
  last_name: z.string().min(1),
  role: z.enum(['CEO_ADMIN', 'HQ_REGULATORY', 'COUNTRY_REGULATORY']),
  countries: z.array(z.string()),
  is_active: z.boolean(),
  password: z.string().optional(),
});
type Values = z.infer<typeof schema>;

function UserDialog({
  open,
  onClose,
  user,
  allowedRoles,
}: {
  open: boolean;
  onClose: () => void;
  user: User | null;
  allowedRoles: Role[];
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const countries = useCountries();
  const { create, update } = useUserMutations();
  const { control, register, handleSubmit, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: user
      ? {
          email: user.email,
          first_name: user.first_name,
          last_name: user.last_name,
          role: user.role,
          countries: user.countries,
          is_active: user.is_active ?? true,
          password: '',
        }
      : {
          email: '',
          first_name: '',
          last_name: '',
          role: allowedRoles[allowedRoles.length - 1],
          countries: [],
          is_active: true,
          password: '',
        },
  });
  const role = useWatch({ control, name: 'role' });
  const submit = (values: Values) => {
    const payload = {
      ...values,
      countries: values.role === 'COUNTRY_REGULATORY' ? values.countries : [],
      password: values.password || undefined,
    };
    const m = user ? update.mutateAsync({ id: user.id, ...payload }) : create.mutateAsync(payload);
    void m
      .then(() => {
        enqueueSnackbar(t('admin.users.saved'), { variant: 'success' });
        onClose();
      })
      .catch(() => undefined);
  };
  const error = create.error ?? update.error;
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{user ? t('app.edit') : t('admin.users.create')}</DialogTitle>
      <form onSubmit={handleSubmit(submit)} noValidate>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('admin.users.email')}
              type="email"
              {...register('email')}
              error={!!formState.errors.email}
              helperText={formState.errors.email ? t('auth.invalidEmail') : undefined}
              inputProps={{ 'data-testid': 'user-email' }}
            />
            <Stack direction="row" spacing={2}>
              <TextField
                label={t('admin.users.firstName')}
                fullWidth
                {...register('first_name')}
                error={!!formState.errors.first_name}
              />
              <TextField
                label={t('admin.users.lastName')}
                fullWidth
                {...register('last_name')}
                error={!!formState.errors.last_name}
              />
            </Stack>
            <Controller
              control={control}
              name="role"
              render={({ field }) => (
                <TextField
                  select
                  label={t('admin.users.role')}
                  {...field}
                  inputProps={{ 'data-testid': 'user-role' }}
                >
                  {allowedRoles.map((r) => (
                    <MenuItem key={r} value={r}>
                      {t(`roles.${r}`)}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
            {role === 'COUNTRY_REGULATORY' && (
              <Controller
                control={control}
                name="countries"
                render={({ field }) => (
                  <Autocomplete
                    multiple
                    options={(countries.data ?? []).map((c) => c.iso2)}
                    getOptionLabel={(iso2) => countries.data?.find((c) => c.iso2 === iso2)?.name ?? iso2}
                    value={field.value}
                    onChange={(_e, v) => field.onChange(v)}
                    renderInput={(params) => <TextField {...params} label={t('admin.users.countries')} />}
                  />
                )}
              />
            )}
            <TextField
              label={t('admin.users.password')}
              type="password"
              autoComplete="new-password"
              helperText={user ? t('admin.users.passwordHint') : undefined}
              {...register('password')}
            />
            <Controller
              control={control}
              name="is_active"
              render={({ field }) => (
                <FormControlLabel
                  control={
                    <Switch checked={field.value} onChange={(e) => field.onChange(e.target.checked)} />
                  }
                  label={t('admin.users.active')}
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

export default function UsersAdminPage() {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const me = useAuthStore((s) => s.user);
  const users = useUsers();
  const { remove } = useUserMutations();
  const [dialog, setDialog] = useState<{ open: boolean; user: User | null }>({ open: false, user: null });
  const [deleting, setDeleting] = useState<User | null>(null);
  const admin = isAdmin(me);
  const allowedRoles: Role[] = admin
    ? ['CEO_ADMIN', 'HQ_REGULATORY', 'COUNTRY_REGULATORY']
    : ['COUNTRY_REGULATORY'];
  const canManage = (u: User) => admin || u.role === 'COUNTRY_REGULATORY';

  const columns: GridColDef<User>[] = [
    { field: 'email', headerName: t('admin.users.email'), flex: 1, minWidth: 220 },
    { field: 'first_name', headerName: t('admin.users.firstName'), width: 140 },
    { field: 'last_name', headerName: t('admin.users.lastName'), width: 140 },
    {
      field: 'role',
      headerName: t('admin.users.role'),
      width: 190,
      valueFormatter: (v: Role) => t(`roles.${v}`),
    },
    {
      field: 'countries',
      headerName: t('admin.users.countries'),
      width: 180,
      valueGetter: (_v, row) => row.countries.join(', '),
    },
    {
      field: 'is_active',
      headerName: t('admin.users.active'),
      width: 90,
      renderCell: (p) => (
        <Chip
          size="small"
          label={p.row.is_active === false ? t('app.no') : t('app.yes')}
          color={p.row.is_active === false ? 'default' : 'success'}
        />
      ),
    },
    {
      field: 'actions',
      headerName: t('app.actions'),
      width: 110,
      sortable: false,
      renderCell: (p) =>
        canManage(p.row) && (
          <>
            <IconButton
              size="small"
              onClick={() => setDialog({ open: true, user: p.row })}
              aria-label={t('app.edit')}
            >
              <EditIcon fontSize="small" />
            </IconButton>
            {admin && p.row.id !== me?.id && (
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
        title={t('admin.users.title')}
        subtitle={!admin ? t('admin.users.hqHint') : undefined}
        actions={
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setDialog({ open: true, user: null })}
            data-testid="user-create"
          >
            {t('admin.users.create')}
          </Button>
        }
      />
      <Paper variant="outlined" sx={{ height: 'calc(100vh - 240px)', minHeight: 400 }}>
        <DataGrid
          rows={users.data ?? []}
          columns={columns}
          loading={users.isPending}
          density="compact"
          disableRowSelectionOnClick
          sx={{ border: 0 }}
        />
      </Paper>
      {dialog.open && (
        <UserDialog
          open
          onClose={() => setDialog({ open: false, user: null })}
          user={dialog.user}
          allowedRoles={allowedRoles}
        />
      )}
      <ConfirmDialog
        open={!!deleting}
        title={t('app.confirmDelete')}
        text={deleting?.email}
        onClose={() => setDeleting(null)}
        loading={remove.isPending}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => {
              enqueueSnackbar(t('admin.users.deleted'), { variant: 'success' });
              setDeleting(null);
            },
            onError: (e) => enqueueSnackbar(extractErrorMessage(e), { variant: 'error' }),
          })
        }
      />
    </Box>
  );
}
