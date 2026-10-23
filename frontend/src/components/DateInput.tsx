import { useState, type ReactNode } from 'react';
import { Stack, Typography, type SxProps, type Theme } from '@mui/material';
import EventAvailableIcon from '@mui/icons-material/EventAvailable';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFnsV3';
import { frFR } from '@mui/x-date-pickers/locales';
import { fr } from 'date-fns/locale';
import { isValid } from 'date-fns';
import { addValidity, formatDate, formatSpan, parseApiDate, toApiDate } from '@/lib/dates';

const MIN_DATE = new Date(1980, 0, 1);
// Dix ans devant : la grille des années reste lisible (une fin à 5 ans y figure toujours).
const MAX_DATE = new Date(new Date().getFullYear() + 10, 11, 31);
const LOCALE_TEXT = frFR.components.MuiLocalizationProvider.defaultProps.localeText;

export interface DateInputProps {
  /** AAAA-MM-JJ, ou null/'' quand la date n'est pas renseignée. */
  value: string | null | undefined;
  onChange: (value: string | null) => void;
  onBlur?: () => void;
  label?: ReactNode;
  helperText?: ReactNode;
  error?: boolean;
  required?: boolean;
  disabled?: boolean;
  size?: 'small' | 'medium';
  fullWidth?: boolean;
  /** Attributs de l'élément <input> (data-testid…). */
  inputProps?: Record<string, unknown>;
  sx?: SxProps<Theme>;
  /** Couleur de fond du champ (valeur modifiée sur le classeur, par exemple). */
  background?: string;
  minDate?: Date;
  maxDate?: Date;
}

/**
 * Sélecteur de date JJ/MM/AAAA : on choisit l'année, puis le mois, puis le jour (ou on tape les
 * trois parties au clavier). La valeur échangée reste une date ISO, comme avec l'ancien champ natif.
 */
export function DateInput({
  value,
  onChange,
  onBlur,
  label,
  helperText,
  error,
  required,
  disabled,
  size,
  fullWidth = true,
  inputProps,
  sx,
  background,
  minDate = MIN_DATE,
  maxDate = MAX_DATE,
}: DateInputProps) {
  const external = value || null;
  // Une saisie en cours (jour tapé, mois pas encore) n'est pas une date : on la garde ici sans
  // la remonter, pour que le champ ne s'efface pas sous les doigts.
  const [draft, setDraft] = useState<Date | null>(() => parseApiDate(external));
  const [seen, setSeen] = useState(external);
  if (external !== seen) {
    setSeen(external);
    const current = draft && isValid(draft) ? toApiDate(draft) : null;
    if (current !== external) setDraft(parseApiDate(external));
  }

  return (
    <LocalizationProvider dateAdapter={AdapterDateFns} adapterLocale={fr} localeText={LOCALE_TEXT}>
      <DatePicker
        value={draft}
        onChange={(next) => {
          setDraft(next);
          if (next === null) onChange(null);
          else if (isValid(next) && next >= minDate && next <= maxDate) onChange(toApiDate(next));
        }}
        onClose={onBlur}
        label={label}
        disabled={disabled}
        format="dd/MM/yyyy"
        views={['year', 'month', 'day']}
        openTo="year"
        yearsOrder="desc"
        minDate={minDate}
        maxDate={maxDate}
        reduceAnimations
        sx={sx}
        slotProps={{
          field: { clearable: !required && !disabled },
          textField: {
            size,
            required,
            fullWidth,
            error,
            helperText,
            onBlur,
            inputProps,
            sx: background ? { '& .MuiOutlinedInput-root': { bgcolor: background } } : undefined,
          },
          layout: {
            sx: {
              '& .MuiPickersYear-yearButton.Mui-selected, & .MuiPickersMonth-monthButton.Mui-selected': {
                fontWeight: 800,
              },
            },
          },
          actionBar: { actions: required ? ['today', 'accept'] : ['clear', 'today', 'accept'] },
          toolbar: { hidden: true },
        }}
      />
    </LocalizationProvider>
  );
}

/**
 * Validité d'une période calculée sous les dates : « Validité : 5 ans, jusqu'au 03/12/2029 ».
 * Une durée différente de celle du pays est signalée : c'est souvent une date mal relevée.
 */
export function ValidityLine({
  start,
  end,
  years,
  auto,
}: {
  start: string | null | undefined;
  end: string | null | undefined;
  years: number;
  /** Fin calculée par l'application (et non saisie). */
  auto?: boolean;
}) {
  const span = formatSpan(start, end);
  if (!start) {
    return (
      <Typography variant="caption" color="text.secondary" data-testid="validity-line">
        Choisissez la date de début : la fin se calcule sur {years} ans.
      </Typography>
    );
  }
  if (!end || !span) {
    return (
      <Typography variant="caption" color="error" data-testid="validity-line">
        La date de fin doit suivre la date de début.
      </Typography>
    );
  }
  const expected = formatSpan(start, addValidity(start, years));
  const off = span !== expected;
  return (
    <Stack
      direction="row"
      spacing={0.75}
      sx={{ alignItems: 'center', color: off ? 'warning.dark' : 'success.dark' }}
      data-testid="validity-line"
    >
      {off ? <WarningAmberIcon sx={{ fontSize: 16 }} /> : <EventAvailableIcon sx={{ fontSize: 16 }} />}
      <Typography variant="caption" sx={{ fontWeight: 600 }}>
        Validité : {span}, jusqu'au {formatDate(end)}
        {auto ? ' (calculée)' : ''}
        {off ? ` — la durée du pays est de ${years} ans` : ''}
      </Typography>
    </Stack>
  );
}
