import { useEffect } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
} from '@mui/material';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useProductMutations, useRanges } from '@/api/hooks/useCatalog';
import type { Product } from '@/api/types';
import { extractErrorMessage } from '@/api/client';

const schema = z.object({
  name: z.string().min(1),
  range: z.string().min(1),
  dci: z.string(),
  dosage: z.string(),
  form: z.string(),
  presentation: z.string(),
  is_active: z.boolean(),
  aliases: z.string(),
});
type Values = z.infer<typeof schema>;

const toValues = (p?: Product | null): Values => ({
  name: p?.name ?? '',
  range: p?.range ?? '',
  dci: p?.dci ?? '',
  dosage: p?.dosage ?? '',
  form: p?.form ?? '',
  presentation: p?.presentation ?? '',
  is_active: p?.is_active ?? true,
  aliases: p?.aliases.join('\n') ?? '',
});

export function ProductFormDialog({
  open,
  onClose,
  product,
}: {
  open: boolean;
  onClose: () => void;
  product?: Product | null;
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const ranges = useRanges();
  const { create, update } = useProductMutations();
  const { control, register, handleSubmit, reset, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: toValues(product),
  });
  useEffect(() => {
    if (open) reset(toValues(product));
  }, [open, product, reset]);

  const submit = (values: Values) => {
    const payload = {
      ...values,
      aliases: values.aliases
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean),
    };
    const m = product ? update.mutateAsync({ id: product.id, ...payload }) : create.mutateAsync(payload);
    void m
      .then(() => {
        enqueueSnackbar(t('products.saved'), { variant: 'success' });
        onClose();
      })
      .catch(() => undefined);
  };
  const error = create.error ?? update.error;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{product ? t('app.edit') : t('products.create')}</DialogTitle>
      <form onSubmit={handleSubmit(submit)} noValidate>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('products.name')}
              {...register('name')}
              error={!!formState.errors.name}
              helperText={formState.errors.name ? t('app.required') : undefined}
            />
            <Controller
              control={control}
              name="range"
              render={({ field, fieldState }) => (
                <TextField
                  select
                  label={t('products.range')}
                  {...field}
                  error={!!fieldState.error}
                  helperText={fieldState.error ? t('app.required') : undefined}
                >
                  {(ranges.data ?? []).map((r) => (
                    <MenuItem key={r.id} value={r.id}>
                      {r.label}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
            <Stack direction="row" spacing={2}>
              <TextField label={t('products.dci')} fullWidth {...register('dci')} />
              <TextField label={t('products.dosage')} fullWidth {...register('dosage')} />
            </Stack>
            <Stack direction="row" spacing={2}>
              <TextField label={t('products.form')} fullWidth {...register('form')} />
              <TextField label={t('products.presentation')} fullWidth {...register('presentation')} />
            </Stack>
            <TextField label={t('products.aliases')} multiline minRows={2} {...register('aliases')} />
            <Controller
              control={control}
              name="is_active"
              render={({ field }) => (
                <FormControlLabel
                  control={
                    <Switch checked={field.value} onChange={(e) => field.onChange(e.target.checked)} />
                  }
                  label={t('products.active')}
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
