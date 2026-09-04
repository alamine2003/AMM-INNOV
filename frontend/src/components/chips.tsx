import { Chip, type ChipProps } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { AlertStatus, AmmStatus, DossierState, Severity, Urgency, WorkflowStatus } from '@/api/types';
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

export function StatusChip({ value, ...rest }: Base & { value: AmmStatus }) {
  const { t } = useTranslation();
  return (
    <Chip
      label={t(`status.${value}`)}
      data-testid={`status-chip-${value}`}
      {...colored(STATUS_COLORS[value], rest)}
    />
  );
}

export function UrgencyChip({ value, ...rest }: Base & { value: Urgency }) {
  const { t } = useTranslation();
  return (
    <Chip
      label={t(`urgency.${value}`)}
      data-testid={`urgency-chip-${value}`}
      {...colored(URGENCY_COLORS[value], rest)}
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
