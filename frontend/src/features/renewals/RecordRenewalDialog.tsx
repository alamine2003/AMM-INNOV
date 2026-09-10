import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from '@mui/material';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { useCountries } from '@/api/hooks/useCatalog';
import { useCreateRenewal } from '@/api/hooks/useRenewals';
import type { Amm } from '@/api/types';
import { DateField } from '@/components/DateField';
import { formatDate, todayIso } from '@/lib/dates';
import { projectObtainedRenewal } from '@/lib/urgency';

const schema = z.object({
  number: z.string().trim().min(1),
  start_date: z.string().nullable(),
  decision_date: z.string().nullable().optional(),
  end_date: z.string().nullable().optional(),
  notes: z.string().optional(),
});
type Values = z.infer<typeof schema>;

/**
 * Enregistre un renouvellement déjà accordé par l'autorité (sa décision est en main), sans
 * rejouer le workflow. Le serveur calcule l'échéance et recalcule le statut de l'AMM.
 */
export function RecordRenewalDialog({
  amm,
  open,
  onClose,
}: {
  amm: Amm;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const create = useCreateRenewal(amm.id);
  const countries = useCountries();
  const validityYears = countries.data?.find((c) => c.iso2 === amm.country_iso2)?.validity_years ?? 5;

  const { control, register, handleSubmit, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      number: '',
      start_date: null,
      decision_date: todayIso(),
      end_date: null,
      notes: '',
    },
  });
  const [startDate, endDate] = useWatch({ control, name: ['start_date', 'end_date'] });
  const projection = projectObtainedRenewal(startDate, validityYears, endDate);

  const submit = (values: Values) =>
    create.mutate(
      {
        workflow_status: 'OBTENU',
        number: values.number.trim(),
        start_date: values.start_date,
        decision_date: values.decision_date || null,
        end_date: values.end_date || null,
        notes: values.notes || '',
      },
      {
        onSuccess: () => {
          enqueueSnackbar(t('renewals.recordDone'), { variant: 'success' });
          onClose();
        },
        onError: (error) => enqueueSnackbar(extractErrorMessage(error), { variant: 'error' }),
      },
    );

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="record-dialog">
      <DialogTitle>{t('renewals.recordTitle')}</DialogTitle>
      <form onSubmit={handleSubmit(submit)} noValidate>
        <DialogContent>
          <Stack spacing={2}>
            <Alert severity="info">{t('renewals.recordHelp', { years: validityYears })}</Alert>
            <TextField
              label={t('renewals.number')}
              required
              error={!!formState.errors.number}
              helperText={formState.errors.number ? t('renewals.numberRequired') : undefined}
              inputProps={{ 'data-testid': 'record-number' }}
              {...register('number')}
            />
            <DateField
              control={control}
              name="start_date"
              label={t('renewals.startDate')}
              required
              helperText={formState.errors.start_date ? t('renewals.startRequired') : t('renewals.startHelp')}
              error={!!formState.errors.start_date}
              inputProps={{ 'data-testid': 'record-start' }}
            />
            <DateField control={control} name="decision_date" label={t('renewals.decisionDate')} />
            <DateField
              control={control}
              name="end_date"
              label={t('renewals.endDate')}
              helperText={t('renewals.endOverride', { years: validityYears })}
              inputProps={{ 'data-testid': 'record-end' }}
            />
            <TextField label={t('renewals.notes')} multiline minRows={2} {...register('notes')} />
            {projection.end && (
              <Alert
                severity={projection.status === 'VALIDE' ? 'success' : 'warning'}
                data-testid="renewal-projection"
              >
                {t('renewals.computedEnd', { date: formatDate(projection.end) })}{' '}
                {projection.status === 'VALIDE'
                  ? t('renewals.willBecomeValid')
                  : t('renewals.willStayExpired')}
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('app.cancel')}</Button>
          <Button type="submit" variant="contained" disabled={create.isPending} data-testid="record-submit">
            {t('app.save')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
