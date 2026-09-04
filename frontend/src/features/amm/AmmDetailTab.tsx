import { useEffect } from 'react';
import { Alert, Button, Grid2 as Grid, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useUpdateAmm } from '@/api/hooks/useAmms';
import type { Amm } from '@/api/types';
import { DateField } from '@/components/DateField';
import { DOSSIER_STATES } from '@/lib/urgency';
import { formatDate, formatDateTime } from '@/lib/dates';
import { extractErrorMessage } from '@/api/client';

const schema = z.object({
  original_number: z.string().nullable(),
  original_start_date: z.string().nullable(),
  original_end_date: z.string().nullable(),
  dossier_state: z.enum(['COMPLET', 'INCOMPLET', 'INCONNU']),
  notes: z.string(),
});
type Values = z.infer<typeof schema>;

export function AmmDetailTab({ amm, editable }: { amm: Amm; editable: boolean }) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const update = useUpdateAmm();
  const { control, register, handleSubmit, reset, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      original_number: amm.original_number ?? '',
      original_start_date: amm.original_start_date,
      original_end_date: amm.original_end_date,
      dossier_state: amm.dossier_state,
      notes: amm.notes ?? '',
    },
  });

  useEffect(() => {
    reset({
      original_number: amm.original_number ?? '',
      original_start_date: amm.original_start_date,
      original_end_date: amm.original_end_date,
      dossier_state: amm.dossier_state,
      notes: amm.notes ?? '',
    });
  }, [amm, reset]);

  const submit = (values: Values) => {
    const payload: Record<string, unknown> = { ...values, original_number: values.original_number || null };
    if (values.original_end_date !== amm.original_end_date)
      payload.original_end_date_manual = !!values.original_end_date;
    update.mutate(
      { id: amm.id, ...payload },
      { onSuccess: () => enqueueSnackbar(t('amm.updated'), { variant: 'success' }) },
    );
  };

  const info = (label: string, value: React.ReactNode) => (
    <Grid size={{ xs: 12, sm: 6, md: 3 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body1">{value}</Typography>
    </Grid>
  );

  return (
    <form onSubmit={handleSubmit(submit)} noValidate data-testid="amm-detail-form">
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {info(t('amm.fields.status'), t(`status.${amm.status}`))}
        {info(t('amm.fields.urgency'), t(`urgency.${amm.urgency}`))}
        {info(t('amm.fields.effectiveEnd'), formatDate(amm.effective_end_date))}
        {info(t('amm.fields.filingDeadline'), formatDate(amm.filing_deadline))}
        {info(t('amm.fields.hasScan'), amm.has_current_scan ? t('app.yes') : t('app.no'))}
        {info(t('amm.fields.updatedAt'), formatDateTime(amm.updated_at))}
        {amm.current_renewal &&
          info(
            t('renewals.sequence', { n: amm.current_renewal.sequence }),
            `${t(`workflow.${amm.current_renewal.workflow_status}`)}${amm.current_renewal.number ? ` — ${amm.current_renewal.number}` : ''}`,
          )}
      </Grid>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 4 }}>
          <TextField
            label={t('amm.fields.originalNumber')}
            fullWidth
            disabled={!editable}
            {...register('original_number')}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <DateField
            control={control}
            name="original_start_date"
            label={t('amm.fields.originalStart')}
            disabled={!editable}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <DateField
            control={control}
            name="original_end_date"
            label={t('amm.fields.originalEnd')}
            disabled={!editable}
            helperText={amm.original_end_date_manual ? t('amm.fields.endManual') : undefined}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <Controller
            control={control}
            name="dossier_state"
            render={({ field }) => (
              <TextField
                select
                fullWidth
                label={t('amm.fields.dossierState')}
                disabled={!editable}
                {...field}
              >
                {DOSSIER_STATES.map((d) => (
                  <MenuItem key={d} value={d}>
                    {t(`dossier.${d}`)}
                  </MenuItem>
                ))}
              </TextField>
            )}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 8 }}>
          <TextField
            label={t('amm.fields.notes')}
            fullWidth
            multiline
            minRows={2}
            disabled={!editable}
            {...register('notes')}
          />
        </Grid>
      </Grid>
      {update.isError && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {extractErrorMessage(update.error)}
        </Alert>
      )}
      {editable && (
        <Stack direction="row" spacing={1} sx={{ mt: 2 }} justifyContent="flex-end">
          <Button onClick={() => reset()} disabled={!formState.isDirty}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" variant="contained" disabled={!formState.isDirty || update.isPending}>
            {t('app.save')}
          </Button>
        </Stack>
      )}
    </form>
  );
}
