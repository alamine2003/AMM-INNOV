import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid2 as Grid,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EventNoteIcon from '@mui/icons-material/EventNote';
import UndoIcon from '@mui/icons-material/Undo';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useCreateRenewal, useRenewals } from '@/api/hooks/useRenewals';
import type { Amm, Renewal, WorkflowStatus } from '@/api/types';
import { WorkflowChip } from '@/components/chips';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { formatDate } from '@/lib/dates';
import { TERMINAL_STATES, WORKFLOW_COLORS, WORKFLOW_TRANSITIONS } from '@/lib/urgency';
import { extractErrorMessage } from '@/api/client';
import { CancelRenewalDialog } from './CancelRenewalDialog';
import { RecordRenewalDialog } from './RecordRenewalDialog';
import { TransitionDialog } from './TransitionDialog';

function RenewalCard({
  renewal,
  editable,
  cancellable,
  onTransition,
  onCancel,
}: {
  renewal: Renewal;
  editable: boolean;
  cancellable: boolean;
  onTransition: (r: Renewal, to: WorkflowStatus) => void;
  onCancel: (r: Renewal) => void;
}) {
  const { t } = useTranslation();
  const transitions = WORKFLOW_TRANSITIONS[renewal.workflow_status];
  const field = (label: string, value: string | null | undefined) => (
    <Grid size={{ xs: 6, sm: 4, md: 2 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2">{value || '—'}</Typography>
    </Grid>
  );
  return (
    <Card
      variant="outlined"
      sx={{ borderLeft: 4, borderLeftColor: WORKFLOW_COLORS[renewal.workflow_status] }}
      data-testid={`renewal-${renewal.sequence}`}
    >
      <CardContent>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            {t('renewals.sequence', { n: renewal.sequence })}
          </Typography>
          <WorkflowChip value={renewal.workflow_status} />
          <Box sx={{ flexGrow: 1 }} />
          {editable &&
            transitions.map((to) => (
              <Button
                key={to}
                size="small"
                variant={to === 'ABANDONNE' ? 'text' : 'outlined'}
                color={to === 'ABANDONNE' || to === 'REJETE' ? 'error' : 'primary'}
                onClick={() => onTransition(renewal, to)}
                data-testid={`transition-${to}`}
              >
                {t('renewals.transitionTo', { state: t(`workflow.${to}`) })}
              </Button>
            ))}
          {editable && TERMINAL_STATES.includes(renewal.workflow_status) && (
            <Typography variant="caption" color="text.secondary">
              {t('renewals.terminal')}
            </Typography>
          )}
          {editable && cancellable && (
            <Tooltip title={t('renewals.cancelHelp')}>
              <IconButton
                size="small"
                color="error"
                onClick={() => onCancel(renewal)}
                aria-label={t('renewals.cancel')}
                data-testid={`renewal-cancel-${renewal.sequence}`}
              >
                <UndoIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Stack>
        <Grid container spacing={2}>
          {field(t('renewals.filingDate'), formatDate(renewal.filing_date))}
          {field(t('renewals.decisionDate'), formatDate(renewal.decision_date))}
          {field(t('renewals.number'), renewal.number)}
          {field(t('renewals.startDate'), formatDate(renewal.start_date))}
          {field(t('renewals.endDate'), formatDate(renewal.end_date))}
          {field(t('renewals.notes'), renewal.notes)}
        </Grid>
      </CardContent>
    </Card>
  );
}

export function RenewalsTab({ amm, editable }: { amm: Amm; editable: boolean }) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const renewals = useRenewals(amm.id);
  const create = useCreateRenewal(amm.id);
  const [dialog, setDialog] = useState<{ renewal: Renewal; to: WorkflowStatus } | null>(null);
  const [recording, setRecording] = useState(false);
  const [cancelling, setCancelling] = useState<Renewal | null>(null);

  if (renewals.isPending) return <LoadingBlock />;
  if (renewals.isError) return <ErrorBlock error={renewals.error} onRetry={() => renewals.refetch()} />;

  const hasOpen = renewals.data.some((r) => !TERMINAL_STATES.includes(r.workflow_status));
  const lastSequence = Math.max(0, ...renewals.data.map((r) => r.sequence));

  return (
    <Box>
      {editable && amm.status === 'EXPIRE' && !hasOpen && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t('renewals.expiredHint')}
        </Alert>
      )}
      {editable && (
        <Stack
          direction="row"
          spacing={1}
          flexWrap="wrap"
          useFlexGap
          sx={{ justifyContent: 'flex-end', mb: 2 }}
        >
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setRecording(true)}
            data-testid="renewal-record"
          >
            {t('renewals.add')}
          </Button>
          <Button
            variant="text"
            startIcon={<EventNoteIcon />}
            disabled={hasOpen || create.isPending}
            onClick={() =>
              create.mutate(
                {},
                {
                  onSuccess: () => enqueueSnackbar(t('renewals.created'), { variant: 'success' }),
                  onError: (e) => enqueueSnackbar(extractErrorMessage(e), { variant: 'error' }),
                },
              )
            }
            data-testid="renewal-create"
          >
            {t('renewals.plan')}
          </Button>
        </Stack>
      )}
      {editable && hasOpen && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('renewals.openCompletes')}
        </Alert>
      )}
      {/* Frise du plus récent au plus ancien, AMM d'origine en bas */}
      <Stack
        spacing={2}
        sx={{
          position: 'relative',
          pl: { sm: 3 },
          '&::before': {
            content: '""',
            position: 'absolute',
            left: 8,
            top: 0,
            bottom: 0,
            width: 2,
            bgcolor: 'divider',
            display: { xs: 'none', sm: 'block' },
          },
        }}
      >
        {renewals.data.length === 0 && <EmptyBlock text={t('renewals.empty')} />}
        {renewals.data.map((r) => (
          <RenewalCard
            key={r.id}
            renewal={r}
            editable={editable}
            // Seul le plus récent s'annule : revenir en arrière, ce n'est pas trouer l'historique.
            cancellable={r.sequence === lastSequence}
            onTransition={(renewal, to) => setDialog({ renewal, to })}
            onCancel={setCancelling}
          />
        ))}
        <Card
          variant="outlined"
          sx={{ borderLeft: 4, borderLeftColor: 'grey.500' }}
          data-testid="renewal-original"
        >
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                {t('renewals.original')}
              </Typography>
              <Chip size="small" label={amm.original_number ?? '—'} variant="outlined" />
            </Stack>
            <Typography variant="body2">
              {formatDate(amm.original_start_date)} → {formatDate(amm.original_end_date)}
            </Typography>
          </CardContent>
        </Card>
      </Stack>
      {recording && <RecordRenewalDialog amm={amm} open onClose={() => setRecording(false)} />}
      {cancelling && (
        <CancelRenewalDialog amm={amm} renewal={cancelling} open onClose={() => setCancelling(null)} />
      )}
      {dialog && (
        <TransitionDialog
          ammId={amm.id}
          renewal={dialog.renewal}
          to={dialog.to}
          open
          onClose={() => setDialog(null)}
        />
      )}
    </Box>
  );
}
