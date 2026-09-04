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
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useTransitionRenewal } from '@/api/hooks/useRenewals';
import type { Renewal, WorkflowStatus } from '@/api/types';
import { DateField } from '@/components/DateField';
import { requiredFieldsFor } from '@/lib/urgency';
import { extractErrorMessage } from '@/api/client';
import { todayIso } from '@/lib/dates';

const base = z.object({
  filing_date: z.string().nullable().optional(),
  decision_date: z.string().nullable().optional(),
  number: z.string().optional(),
  start_date: z.string().nullable().optional(),
  end_date: z.string().nullable().optional(),
  notes: z.string().optional(),
});
type Values = z.infer<typeof base>;

export function buildTransitionSchema(to: WorkflowStatus, t: (k: string) => string) {
  const required = requiredFieldsFor(to);
  return base.superRefine((v, ctx) => {
    if (required.includes('filing_date') && !v.filing_date)
      ctx.addIssue({ code: 'custom', path: ['filing_date'], message: t('renewals.filingRequired') });
    if (required.includes('number') && !v.number?.trim())
      ctx.addIssue({ code: 'custom', path: ['number'], message: t('renewals.numberRequired') });
    if (required.includes('start_date') && !v.start_date)
      ctx.addIssue({ code: 'custom', path: ['start_date'], message: t('renewals.startRequired') });
  });
}

export function TransitionDialog({
  ammId,
  renewal,
  to,
  open,
  onClose,
}: {
  ammId: string;
  renewal: Renewal;
  to: WorkflowStatus;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const transition = useTransitionRenewal(ammId);
  const required = requiredFieldsFor(to);
  const { control, register, handleSubmit, formState } = useForm<Values>({
    resolver: zodResolver(buildTransitionSchema(to, t)),
    defaultValues: {
      filing_date: renewal.filing_date ?? (to === 'DEPOSE' ? null : undefined),
      decision_date: renewal.decision_date ?? (to === 'OBTENU' || to === 'REJETE' ? todayIso() : undefined),
      number: renewal.number ?? '',
      start_date: renewal.start_date ?? null,
      end_date: renewal.end_date ?? null,
      notes: '',
    },
  });

  const submit = (values: Values) => {
    const payload = Object.fromEntries(
      Object.entries(values).filter(([, v]) => v !== null && v !== undefined && v !== ''),
    ) as Record<string, string>;
    transition.mutate(
      { renewalId: renewal.id, to, ...payload },
      {
        onSuccess: () => {
          enqueueSnackbar(t('renewals.transitionDone'), { variant: 'success' });
          onClose();
        },
      },
    );
  };

  const showFiling = to === 'DEPOSE' || to === 'EN_INSTRUCTION';
  const showDecision = to === 'OBTENU' || to === 'REJETE';
  const showObtained = to === 'OBTENU';

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="transition-dialog">
      <DialogTitle>{t('renewals.transitionTitle', { state: t(`workflow.${to}`) })}</DialogTitle>
      <form onSubmit={handleSubmit(submit)} noValidate>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {showFiling && (
              <DateField
                control={control}
                name="filing_date"
                label={t('renewals.filingDate')}
                required={required.includes('filing_date')}
                inputProps={{ 'data-testid': 'filing_date' }}
              />
            )}
            {showDecision && (
              <DateField control={control} name="decision_date" label={t('renewals.decisionDate')} />
            )}
            {showObtained && (
              <>
                <TextField
                  label={t('renewals.number')}
                  required
                  {...register('number')}
                  error={!!formState.errors.number}
                  helperText={formState.errors.number?.message}
                  inputProps={{ 'data-testid': 'number' }}
                />
                <DateField
                  control={control}
                  name="start_date"
                  label={t('renewals.startDate')}
                  required
                  inputProps={{ 'data-testid': 'start_date' }}
                />
                <DateField
                  control={control}
                  name="end_date"
                  label={t('renewals.endDate')}
                  helperText={t('amm.fields.endManual')}
                />
              </>
            )}
            <TextField label={t('renewals.notes')} multiline minRows={2} {...register('notes')} />
            {transition.isError && <Alert severity="error">{extractErrorMessage(transition.error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('app.cancel')}</Button>
          <Button
            type="submit"
            variant="contained"
            disabled={transition.isPending}
            data-testid="transition-submit"
          >
            {t('app.confirm')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
