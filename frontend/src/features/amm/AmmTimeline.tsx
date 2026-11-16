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
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
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

/** États d'un renouvellement non encore obtenu, vers la clé de leur libellé (en minuscules, dans une phrase). */
const PENDING_LABELS: Record<string, string> = {
  PLANIFIE: 'ammPages.timeline.pending.PLANIFIE',
  EN_PREPARATION: 'ammPages.timeline.pending.EN_PREPARATION',
  DEPOSE: 'ammPages.timeline.pending.DEPOSE',
  EN_INSTRUCTION: 'ammPages.timeline.pending.EN_INSTRUCTION',
};

/** Le document actuel : dernier renouvellement OBTENU et daté, sinon l'origine (même règle que le serveur). */
export function currentStageId(renewals: Renewal[]): string {
  const obtained = renewals.filter((r) => r.workflow_status === 'OBTENU' && r.end_date);
  if (!obtained.length) return 'origin';
  return obtained.reduce((a, b) => (b.sequence > a.sequence ? b : a)).id;
}

export function buildStages(amm: Amm, renewals: Renewal[], t: TFunction): Stage[] {
  const obtained = renewals
    .filter((r) => r.workflow_status === 'OBTENU' && r.end_date)
    .sort((a, b) => a.sequence - b.sequence);
  return [
    {
      id: 'origin',
      title: t('ammPages.timeline.origin'),
      number: amm.original_number,
      start: amm.original_start_date,
      end: amm.original_end_date,
    },
    ...obtained.map((r, index) => ({
      id: r.id,
      title: t('ammPages.timeline.renewal', { n: index + 1 }),
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
  const { t } = useTranslation();
  const renewals = useRenewals(amm.id);
  // Tant que les renouvellements ne sont pas lus, le document actuel n'est pas connu.
  if (renewals.isPending) return <LinearProgress aria-label={t('ammPages.timeline.loading')} />;
  if (renewals.isError) return <ErrorBlock error={renewals.error} onRetry={() => renewals.refetch()} />;
  const list = renewals.data;
  const stages = buildStages(amm, list, t);
  const current = currentStageId(list);
  const pending = list.find((r) => r.workflow_status in PENDING_LABELS);
  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="amm-timeline">
      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
        {t('ammPages.timeline.heading')}
      </Typography>
      <Stepper orientation="vertical" nonLinear activeStep={-1} aria-label={t('ammPages.timeline.ariaLabel')}>
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
                      label={t('ammPages.timeline.currentDocument')}
                      data-testid="current-document"
                    />
                  )}
                </Stack>
              </StepLabel>
              <StepContent>
                <Typography variant="body2">
                  {t('ammPages.timeline.number', { number: stage.number || '—' })}
                </Typography>
                {isCurrent && (
                  <Typography
                    variant="caption"
                    color={amm.has_current_scan ? 'success.main' : 'warning.main'}
                    data-testid="current-scan"
                  >
                    {amm.has_current_scan
                      ? t('ammPages.timeline.scanAttached')
                      : t('ammPages.timeline.scanMissing')}
                  </Typography>
                )}
              </StepContent>
            </Step>
          );
        })}
      </Stepper>
      {pending && (
        <Alert severity="info" sx={{ mt: 1 }}>
          {t('ammPages.timeline.pendingNotice', {
            state: t(PENDING_LABELS[pending.workflow_status]),
          })}
        </Alert>
      )}
    </Paper>
  );
}
