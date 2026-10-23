import { useState } from 'react';
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
import { Controller, useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { useCreateAmm } from '@/api/hooks/useAmms';
import { useCountries, useProductSearch } from '@/api/hooks/useCatalog';
import type { Amm, Product } from '@/api/types';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { DateField } from '@/components/DateField';
import { DateInput, ValidityLine } from '@/components/DateInput';
import { addValidity } from '@/lib/dates';
import { extractErrorMessage } from '@/api/client';
import { isHqOrAdmin, useAuthStore } from '@/features/auth/authStore';
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
  const [productInput, setProductInput] = useState('');
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const products = useProductSearch(useDebouncedValue(productInput, 250));
  const productOptions = selectedProduct
    ? [selectedProduct, ...(products.data ?? []).filter((p) => p.id !== selectedProduct.id)]
    : (products.data ?? []);
  const create = useCreateAmm();
  const user = useAuthStore((s) => s.user);
  const allowedCountries = (countries.data ?? []).filter(
    (c) => user?.role !== 'COUNTRY_REGULATORY' || user.countries.includes(c.iso2),
  );
  const canCreateProduct = isHqOrAdmin(user);

  const { control, handleSubmit, register, reset, formState, setValue } = useForm<AmmFormValues>({
    resolver: zodResolver(ammSchema),
    defaultValues: {
      product: '',
      country: '',
      original_number: '',
      original_start_date: null,
      original_end_date: null,
      notes: '',
    },
  });

  const [countryId, start, end] = useWatch({
    control,
    name: ['country', 'original_start_date', 'original_end_date'],
  });
  const years = countries.data?.find((c) => c.id === countryId)?.validity_years ?? 5;

  const submit = (values: AmmFormValues) => {
    create.mutate(
      {
        ...values,
        original_number: values.original_number || null,
        // Fin = début + durée du pays : calculée par le serveur, pas « saisie à la main ».
        original_end_date_manual:
          !!values.original_end_date &&
          values.original_end_date !== addValidity(values.original_start_date, years),
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
                  options={productOptions}
                  getOptionLabel={(p) => p.name}
                  isOptionEqualToValue={(a, b) => a.id === b.id}
                  filterOptions={(x) => x}
                  loading={products.isFetching}
                  noOptionsText={
                    // Un réglementaire pays ne crée pas de produit : sans ce rappel, il reste
                    // devant une liste vide sans savoir à qui s'adresser.
                    productInput
                      ? t(canCreateProduct ? 'amm.productNoMatch' : 'amm.productAskHq')
                      : t('amm.productTypeToSearch')
                  }
                  value={selectedProduct}
                  inputValue={productInput}
                  onInputChange={(_e, v) => setProductInput(v)}
                  onChange={(_e, v) => {
                    setSelectedProduct(v);
                    field.onChange(v?.id ?? '');
                  }}
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
            <Controller
              control={control}
              name="original_start_date"
              render={({ field }) => (
                <DateInput
                  label={t('amm.fields.originalStart')}
                  value={field.value}
                  onBlur={field.onBlur}
                  onChange={(value) => {
                    field.onChange(value);
                    setValue('original_end_date', addValidity(value, years));
                  }}
                />
              )}
            />
            <DateField
              control={control}
              name="original_end_date"
              label={t('amm.fields.originalEnd')}
              helperText={`Calculée : début + ${years} ans (modifiable)`}
            />
            {start && <ValidityLine start={start} end={end} years={years} />}
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
