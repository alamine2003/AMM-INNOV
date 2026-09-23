import {
  Alert,
  Chip,
  LinearProgress,
  Paper,
  Stack,
  Step,
  StepContent,
  StepLabel,
  Stepper,
  Typography,
} from '@mui/material';
import { useRenewals } from '@/api/hooks/useRenewals';
import type { Amm, Renewal } from '@/api/types';
import { ErrorBlock } from '@/components/QueryState';
import { formatDate } from '@/lib/dates';

interface Stage {
  id: string;
  title: string;
  number: string | null;
  start: string | null;
  end: string | null;
}

const PENDING_LABELS: Record<string, string> = {
  PLANIFIE: 'planifié',
  EN_PREPARATION: 'en préparation',
  DEPOSE: 'déposé',
  EN_INSTRUCTION: 'en instruction',
};

/** Le document actuel : dernier renouvellement OBTENU et daté, sinon l'origine (même règle que le serveur). */
export function currentStageId(renewals: Renewal[]): string {
  const obtained = renewals.filter((r) => r.workflow_status === 'OBTENU' && r.end_date);
  if (!obtained.length) return 'origin';
  return obtained.reduce((a, b) => (b.sequence > a.sequence ? b : a)).id;
}

export function buildStages(amm: Amm, renewals: Renewal[]): Stage[] {
  const obtained = renewals
    .filter((r) => r.workflow_status === 'OBTENU' && r.end_date)
    .sort((a, b) => a.sequence - b.sequence);
  return [
    {
      id: 'origin',
      title: 'Origine',
      number: amm.original_number,
      start: amm.original_start_date,
      end: amm.original_end_date,
    },
    ...obtained.map((r, index) => ({
      id: r.id,
      title: `Renouvellement ${index + 1}`,
      number: r.number,
      start: r.start_date,
      end: r.end_date,
    })),
  ];
}

/**
 * Frise de l'AMM : l'origine puis les renouvellements OBTENUS, le document actuel mis en évidence.
 * Un renouvellement non obtenu n'y figure pas : il n'est pris en compte qu'une fois obtenu.
 */
export function AmmTimeline({ amm }: { amm: Amm }) {
  const renewals = useRenewals(amm.id);
  // Tant que les renouvellements ne sont pas lus, le document actuel n'est pas connu.
  if (renewals.isPending) return <LinearProgress aria-label="Chargement de la frise" />;
  if (renewals.isError) return <ErrorBlock error={renewals.error} onRetry={() => renewals.refetch()} />;
  const list = renewals.data;
  const stages = buildStages(amm, list);
  const current = currentStageId(list);
  const pending = list.find((r) => r.workflow_status in PENDING_LABELS);
  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="amm-timeline">
      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
        Origine → renouvellements obtenus
      </Typography>
      <Stepper orientation="vertical" nonLinear activeStep={-1} aria-label="Frise de l’AMM">
        {stages.map((stage, index) => {
          const isCurrent = stage.id === current;
          return (
            <Step key={stage.id} active expanded completed={false} data-testid={`timeline-${stage.id}`}>
              <StepLabel icon={index + 1}>
                <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
                  <Typography fontWeight={isCurrent ? 700 : 500}>{stage.title}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {formatDate(stage.start, '?')} → {formatDate(stage.end, '?')}
                  </Typography>
                  {isCurrent && (
                    <Chip
                      size="small"
                      color="primary"
                      label="Document actuel"
                      data-testid="current-document"
                    />
                  )}
                </Stack>
              </StepLabel>
              <StepContent>
                <Typography variant="body2">N° {stage.number || '—'}</Typography>
                {isCurrent && (
                  <Typography
                    variant="caption"
                    color={amm.has_current_scan ? 'success.main' : 'warning.main'}
                    data-testid="current-scan"
                  >
                    {amm.has_current_scan
                      ? 'Scan de la décision rattaché : dossier complet.'
                      : 'Scan de la décision manquant : dossier incomplet.'}
                  </Typography>
                )}
              </StepContent>
            </Step>
          );
        })}
      </Stepper>
      {pending && (
        <Alert severity="info" sx={{ mt: 1 }}>
          Renouvellement {PENDING_LABELS[pending.workflow_status]} : il ne compte qu’une fois obtenu.
        </Alert>
      )}
    </Paper>
  );
}
