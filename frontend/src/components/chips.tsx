import { Chip, type ChipProps } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type {
  AlertStatus,
  AmmStatus,
  DossierState,
  OriginApplication,
  Severity,
  Urgency,
  WorkflowStatus,
} from '@/api/types';
import {
  ALERT_STATUS_COLORS,
  DOSSIER_COLORS,
  SEVERITY_COLORS,
  STATUS_COLORS,
  URGENCY_COLORS,
  WORKFLOW_COLORS,
} from '@/lib/urgency';

type Base = Omit<ChipProps, 'label' | 'color'>;

function colored(color: string, base: Base = {}): ChipProps {
  return {
    size: 'small',
    ...base,
    sx: { bgcolor: color, color: '#fff', fontWeight: 600, ...(base.sx as object) },
  };
}

/** Demande d'AMM d'origine en cours (bleu) ou close sans AMM (gris) : 1.4.1. */
const ORIGIN_COLORS: Record<string, string> = {
  EN_PREPARATION: '#1565c0',
  DEPOSE: '#1565c0',
  EN_INSTRUCTION: '#1565c0',
  REJETE: '#757575',
  ABANDONNE: '#757575',
};

/**
 * Statut de l'AMM ; tant qu'une demande d'origine est suivie (`origin`), c'est elle qui
 * s'affiche, au lieu d'« Échéance inconnue ».
 */
export function StatusChip({
  value,
  origin,
  ...rest
}: Base & { value: AmmStatus; origin?: OriginApplication | null }) {
  const { t } = useTranslation();
  if (origin) {
    return (
      <Chip
        label={t(`originApplication.${origin}`)}
        data-testid={`origin-chip-${origin}`}
        {...colored(ORIGIN_COLORS[origin] ?? '#757575', rest)}
      />
    );
  }
  return (
    <Chip
      label={t(`status.${value}`)}
      data-testid={`status-chip-${value}`}
      {...colored(STATUS_COLORS[value] ?? STATUS_COLORS.INDETERMINE, rest)}
    />
  );
}

export function UrgencyChip({ value, ...rest }: Base & { value: Urgency }) {
  const { t } = useTranslation();
  return (
    <Chip
      label={t(`urgency.${value}`)}
      data-testid={`urgency-chip-${value}`}
      {...colored(URGENCY_COLORS[value] ?? '#757575', rest)}
    />
  );
}

export function WorkflowChip({ value, ...rest }: Base & { value: WorkflowStatus }) {
  const { t } = useTranslation();
  return <Chip label={t(`workflow.${value}`)} {...colored(WORKFLOW_COLORS[value], rest)} />;
}

export function SeverityChip({ value, ...rest }: Base & { value: Severity }) {
  const { t } = useTranslation();
  return <Chip label={t(`severity.${value}`)} {...colored(SEVERITY_COLORS[value], rest)} />;
}

export function AlertStatusChip({ value, ...rest }: Base & { value: AlertStatus }) {
  const { t } = useTranslation();
  return <Chip label={t(`alertStatus.${value}`)} {...colored(ALERT_STATUS_COLORS[value], rest)} />;
}

export function DossierChip({ value, ...rest }: Base & { value: DossierState }) {
  const { t } = useTranslation();
  return (
    <Chip
      label={t(`dossier.${value}`)}
      variant="outlined"
      size="small"
      {...rest}
      sx={{ borderColor: DOSSIER_COLORS[value], color: DOSSIER_COLORS[value], fontWeight: 600 }}
    />
  );
}
