import { useEffect } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Grid2 as Grid,
  TextField,
  Typography,
} from '@mui/material';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { useValidityYears } from '@/api/hooks/useCatalog';
import { useUpdateRenewal } from '@/api/hooks/useRenewals';
import type { Amm, Renewal } from '@/api/types';
import { DateField } from '@/components/DateField';
import { DateInput, ValidityLine } from '@/components/DateInput';
import { addValidity } from '@/lib/dates';

type Values = {
  number: string;
  filing_date: string | null;
  decision_date: string | null;
  start_date: string | null;
  end_date: string | null;
  end_auto: boolean;
  notes: string;
};

function initial(renewal: Renewal): Values {
  return {
    number: renewal.number ?? '',
    filing_date: renewal.filing_date,
    decision_date: renewal.decision_date,
    start_date: renewal.start_date,
    end_date: renewal.end_date,
    end_auto: !renewal.end_date_manual,
    notes: renewal.notes ?? '',
  };
}

/**
 * Corrige un renouvellement déjà enregistré (date faussée par un import, n° mal lu…). Le serveur
 * recalcule la date de fin (sauf si elle est saisie), remet les renouvellements dans l'ordre des
 * dates et recalcule l'échéance et le statut de l'AMM.
 */
export function EditRenewalDialog({
  amm,
  renewal,
  open,
  onClose,
}: {
  amm: Amm;
  renewal: Renewal;
  open: boolean;
  onClose: () => void;
}) {
  const { enqueueSnackbar } = useSnackbar();
  const update = useUpdateRenewal(amm.id);
  const years = useValidityYears(amm.country_iso2);
  const { control, register, handleSubmit, reset, formState, setValue } = useForm<Values>({
    defaultValues: initial(renewal),
  });
  const [endAuto, start, end] = useWatch({ control, name: ['end_auto', 'start_date', 'end_date'] });
  const computedEnd = addValidity(start, years);
  const shownEnd = endAuto ? computedEnd : end;

  useEffect(() => {
    if (open) reset(initial(renewal));
  }, [open, renewal, reset]);

  const submit = (values: Values) => {
    if (values.start_date && values.end_date && !values.end_auto && values.end_date < values.start_date) {
      enqueueSnackbar('La date de fin précède la date de début.', { variant: 'error' });
      return;
    }
    update.mutate(
      {
        renewalId: renewal.id,
        number: values.number.trim(),
        filing_date: values.filing_date || null,
        decision_date: values.decision_date || null,
        start_date: values.start_date || null,
        notes: values.notes,
        // Fin automatique : recalculée depuis la date de début et la durée du pays.
        ...(values.end_auto
          ? { end_date: null, end_date_manual: false }
          : { end_date: values.end_date || null, end_date_manual: !!values.end_date }),
      },
      {
        onSuccess: () => {
          enqueueSnackbar(`Renouvellement ${renewal.sequence} corrigé`, { variant: 'success' });
          onClose();
        },
      },
    );
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="edit-renewal-dialog">
      <form onSubmit={handleSubmit(submit)} noValidate>
        <DialogTitle>Corriger le renouvellement {renewal.sequence}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            L'échéance et le statut de l'AMM sont recalculés ; l'ancienne valeur reste dans l'historique.
          </Typography>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12 }}>
              <TextField label="N° d'AMM" fullWidth {...register('number')} />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <DateField control={control} name="filing_date" label="Date de dépôt" />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <DateField control={control} name="decision_date" label="Date de décision" />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <Controller
                control={control}
                name="start_date"
                render={({ field }) => (
                  <DateInput
                    label="Date de début"
                    value={field.value}
                    onBlur={field.onBlur}
                    onChange={(value) => {
                      field.onChange(value);
                      // Une date de début corrigée refait le calcul de la fin sur la durée du pays.
                      if (value !== start) setValue('end_auto', true, { shouldDirty: true });
                    }}
                  />
                )}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {endAuto ? (
                <DateInput
                  label="Date de fin"
                  value={computedEnd}
                  onChange={() => undefined}
                  disabled
                  helperText={`Début + ${years} ans`}
                />
              ) : (
                <DateField
                  control={control}
                  name="end_date"
                  label="Date de fin"
                  helperText="Saisie à la main"
                />
              )}
            </Grid>
            <Grid size={{ xs: 12 }}>
              <ValidityLine start={start} end={shownEnd} years={years} auto={endAuto} />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Controller
                control={control}
                name="end_auto"
                render={({ field }) => (
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={field.value}
                        onChange={(e) => {
                          field.onChange(e.target.checked);
                          // On repart de la fin calculée pour la retoucher à la main.
                          if (!e.target.checked && computedEnd) setValue('end_date', computedEnd);
                        }}
                      />
                    }
                    label={`Date de fin calculée automatiquement (${years} ans, durée de validité du pays)`}
                  />
                )}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField label="Notes" fullWidth multiline minRows={2} {...register('notes')} />
            </Grid>
          </Grid>
          {update.isError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {extractErrorMessage(update.error)}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Annuler</Button>
          <Button
            type="submit"
            variant="contained"
            disabled={!formState.isDirty || update.isPending}
            data-testid="edit-renewal-save"
          >
            Enregistrer
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
