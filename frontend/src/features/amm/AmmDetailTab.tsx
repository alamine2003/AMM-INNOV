import { useEffect } from 'react';
import { Alert, Box, Button, Grid2 as Grid, Stack, TextField, Typography } from '@mui/material';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useUpdateAmm } from '@/api/hooks/useAmms';
import type { Amm } from '@/api/types';
import { useValidityYears } from '@/api/hooks/useCatalog';
import { DateField } from '@/components/DateField';
import { DateInput, ValidityLine } from '@/components/DateInput';
import { DossierChip, StatusChip } from '@/components/chips';
import { filingDateText } from '@/components/FilingDates';
import { AmmTimeline } from './AmmTimeline';
import { addValidity, formatDate, formatDateTime } from '@/lib/dates';
import { extractErrorMessage } from '@/api/client';

const schema = z.object({
  original_number: z.string().nullable(),
  original_start_date: z.string().nullable(),
  original_end_date: z.string().nullable(),
  notes: z.string(),
});
type Values = z.infer<typeof schema>;

export function AmmDetailTab({ amm, editable }: { amm: Amm; editable: boolean }) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const update = useUpdateAmm();
  const years = useValidityYears(amm.country_iso2);
  const { control, register, handleSubmit, reset, formState, setValue } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      original_number: amm.original_number ?? '',
      original_start_date: amm.original_start_date,
      original_end_date: amm.original_end_date,
      notes: amm.notes ?? '',
    },
  });

  const [start, end] = useWatch({ control, name: ['original_start_date', 'original_end_date'] });

  useEffect(() => {
    reset({
      original_number: amm.original_number ?? '',
      original_start_date: amm.original_start_date,
      original_end_date: amm.original_end_date,
      notes: amm.notes ?? '',
    });
  }, [amm, reset]);

  const submit = (values: Values) => {
    const payload: Record<string, unknown> = { ...values, original_number: values.original_number || null };
    // Fin égale à début + durée du pays : elle reste calculée (et suivra une prochaine correction).
    const auto = values.original_end_date === addValidity(values.original_start_date, years);
    if (
      values.original_end_date !== amm.original_end_date ||
      values.original_start_date !== amm.original_start_date
    )
      payload.original_end_date_manual = !!values.original_end_date && !auto;
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
      <Typography variant="body1" component="div">
        {value}
      </Typography>
    </Grid>
  );

  return (
    <form onSubmit={handleSubmit(submit)} noValidate data-testid="amm-detail-form">
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {info('Titulaire / laboratoire', amm.holder || '—')}
        {info(t('amm.fields.status'), <StatusChip value={amm.status} />)}
        {info(t('amm.fields.urgency'), t(`urgency.${amm.urgency}`))}
        {info(t('amm.fields.effectiveEnd'), formatDate(amm.effective_end_date))}
        {info(
          t('amm.fields.idealFiling'),
          <span title={t('amm.fields.idealFilingHelp')} data-testid="ideal-filing">
            {filingDateText(amm.ideal_filing_date, 'dépassé')}
          </span>,
        )}
        {info(
          t('amm.fields.agencyDeadline'),
          <span title={t('amm.fields.agencyDeadlineHelp')} data-testid="agency-deadline">
            {filingDateText(amm.agency_filing_deadline, 'dépassée')}
          </span>,
        )}
        {info(t('amm.fields.hasScan'), amm.has_current_scan ? t('app.yes') : t('app.no'))}
        {info(t('amm.fields.dossierState'), <DossierChip value={amm.dossier_state} />)}
        {info(t('amm.fields.updatedAt'), formatDateTime(amm.updated_at))}
        {amm.last_renewal &&
          info(
            t('renewals.sequence', { n: amm.last_renewal.sequence }),
            `${t(`workflow.${amm.last_renewal.workflow_status}`)}${amm.last_renewal.number ? ` — ${amm.last_renewal.number}` : ''}`,
          )}
      </Grid>
      <Box sx={{ mb: 3 }}>
        <AmmTimeline amm={amm} />
      </Box>
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
          <Controller
            control={control}
            name="original_start_date"
            render={({ field }) => (
              <DateInput
                label={t('amm.fields.originalStart')}
                value={field.value}
                onBlur={field.onBlur}
                disabled={!editable}
                inputProps={{ 'data-testid': 'original-start' }}
                onChange={(value) => {
                  field.onChange(value);
                  // Début corrigé : la fin se recalcule sur la durée de validité du pays.
                  if (value !== start)
                    setValue('original_end_date', addValidity(value, years), { shouldDirty: true });
                }}
              />
            )}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <DateField
            control={control}
            name="original_end_date"
            label={t('amm.fields.originalEnd')}
            disabled={!editable}
            helperText={
              end && end !== addValidity(start, years) ? t('amm.fields.endManual') : `Début + ${years} ans`
            }
          />
        </Grid>
        {editable && (
          <Grid size={{ xs: 12 }} sx={{ mt: -1 }}>
            <ValidityLine start={start} end={end} years={years} />
          </Grid>
        )}
        <Grid size={{ xs: 12 }}>
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
