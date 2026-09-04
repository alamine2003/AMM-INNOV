import {
  Alert,
  Autocomplete,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { useCreateAmm } from '@/api/hooks/useAmms';
import { useCountries, useProducts } from '@/api/hooks/useCatalog';
import type { Amm } from '@/api/types';
import { DateField } from '@/components/DateField';
import { DOSSIER_STATES } from '@/lib/urgency';
import { extractErrorMessage } from '@/api/client';
import { useAuthStore } from '@/features/auth/authStore';
import { ammSchema, type AmmFormValues } from './ammSchema';

export function AmmCreateDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated?: (amm: Amm) => void;
}) {
  const { t } = useTranslation();
  const countries = useCountries();
  const products = useProducts();
  const create = useCreateAmm();
  const user = useAuthStore((s) => s.user);
  const allowedCountries = (countries.data ?? []).filter(
    (c) => user?.role !== 'COUNTRY_REGULATORY' || user.countries.includes(c.iso2),
  );

  const { control, handleSubmit, register, reset, formState } = useForm<AmmFormValues>({
    resolver: zodResolver(ammSchema),
    defaultValues: {
      product: '',
      country: '',
      original_number: '',
      original_start_date: null,
      original_end_date: null,
      dossier_state: 'INCONNU',
      notes: '',
    },
  });

  const submit = (values: AmmFormValues) => {
    create.mutate(
      {
        ...values,
        original_number: values.original_number || null,
        original_end_date_manual: !!values.original_end_date,
      },
      {
        onSuccess: (amm) => {
          reset();
          onClose();
          onCreated?.(amm);
        },
      },
    );
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('amm.createTitle')}</DialogTitle>
      <form onSubmit={handleSubmit(submit)} noValidate>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Controller
              control={control}
              name="product"
              render={({ field, fieldState }) => (
                <Autocomplete
                  options={products.data ?? []}
                  getOptionLabel={(p) => p.name}
                  value={(products.data ?? []).find((p) => p.id === field.value) ?? null}
                  onChange={(_e, v) => field.onChange(v?.id ?? '')}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label={t('amm.fields.product')}
                      error={!!fieldState.error}
                      helperText={fieldState.error ? t('app.required') : undefined}
                    />
                  )}
                />
              )}
            />
            <Controller
              control={control}
              name="country"
              render={({ field, fieldState }) => (
                <TextField
                  select
                  label={t('amm.fields.country')}
                  {...field}
                  error={!!fieldState.error}
                  helperText={fieldState.error ? t('app.required') : undefined}
                >
                  {allowedCountries.map((c) => (
                    <MenuItem key={c.id} value={c.id}>
                      {c.name}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
            <TextField label={t('amm.fields.originalNumber')} {...register('original_number')} />
            <DateField control={control} name="original_start_date" label={t('amm.fields.originalStart')} />
            <DateField
              control={control}
              name="original_end_date"
              label={t('amm.fields.originalEnd')}
              helperText={t('amm.fields.endManual')}
            />
            <Controller
              control={control}
              name="dossier_state"
              render={({ field }) => (
                <TextField select label={t('amm.fields.dossierState')} {...field}>
                  {DOSSIER_STATES.map((d) => (
                    <MenuItem key={d} value={d}>
                      {t(`dossier.${d}`)}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
            <TextField label={t('amm.fields.notes')} multiline minRows={2} {...register('notes')} />
            {create.isError && <Alert severity="error">{extractErrorMessage(create.error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('app.cancel')}</Button>
          <Button type="submit" variant="contained" disabled={create.isPending || formState.isSubmitting}>
            {t('app.create')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
