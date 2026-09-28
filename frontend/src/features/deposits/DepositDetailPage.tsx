import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid2 as Grid,
  Link as MuiLink,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import SendIcon from '@mui/icons-material/Send';
import { Link, useParams } from 'react-router';
import { useDeposit, useDepositActions } from '@/api/hooks/useDeposits';
import type { DepositDetail } from '@/api/types';
import { Flag } from '@/features/binders/Flag';
import { FilingDates } from '@/components/FilingDates';
import { PageHeader } from '@/components/PageHeader';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { StatusChip } from '@/components/chips';
import { formatDate, formatDateTime } from '@/lib/dates';
import { StageChip } from './DepositsPage';
import {
  DecisionSection,
  DepositSection,
  FollowSection,
  PiecesSection,
  SamplesSection,
  SendSection,
  useFail,
} from './sections';
import { PROCEDURE, activeStep, stepsDone } from './stages';

type Actions = ReturnType<typeof useDepositActions>;

/** Échanges siège ↔ pays, en bulles : les siens à droite, le siège en bleu, le pays en vert. */
function Messages({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const [body, setBody] = useState('');
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'nearest' });
  }, [dossier.messages.length]);
  const submit = () =>
    body.trim() && actions.message.mutate(body.trim(), { onSuccess: () => setBody(''), onError: fail });
  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardHeader
        title="Échanges siège ↔ pays"
        subheader="Chaque message prévient l’autre côté."
        titleTypographyProps={{ variant: 'subtitle1', fontWeight: 700 }}
      />
      <CardContent sx={{ pt: 0 }}>
        <Box sx={{ maxHeight: 380, overflowY: 'auto', mb: 1.5, pr: 0.5 }} data-testid="messages">
          {dossier.messages.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              Pas encore de message.
            </Typography>
          )}
          {dossier.messages.map((message) => (
            <Box
              key={message.id}
              sx={{ display: 'flex', justifyContent: message.mine ? 'flex-end' : 'flex-start', mb: 1 }}
            >
              <Box
                sx={{
                  maxWidth: '85%',
                  px: 1.5,
                  py: 1,
                  borderRadius: 2,
                  borderTopRightRadius: message.mine ? 4 : undefined,
                  borderTopLeftRadius: message.mine ? undefined : 4,
                  bgcolor: message.from_hq ? 'rgba(21, 101, 192, 0.10)' : 'rgba(46, 125, 50, 0.12)',
                }}
              >
                <Typography variant="caption" color="text.secondary" component="div">
                  <strong>{message.author ?? '?'}</strong> · {message.from_hq ? 'Siège' : 'Pays'} ·{' '}
                  {formatDateTime(message.created_at)}
                </Typography>
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                  {message.body}
                </Typography>
              </Box>
            </Box>
          ))}
          <div ref={end} />
        </Box>
        <Stack direction="row" gap={1} alignItems="flex-end">
          <TextField
            size="small"
            fullWidth
            multiline
            maxRows={5}
            label="Votre message"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit();
            }}
          />
          <Button
            variant="contained"
            aria-label="Envoyer le message"
            disabled={!body.trim() || actions.message.isPending}
            onClick={submit}
            sx={{ minWidth: 0, px: 1.5 }}
          >
            <SendIcon fontSize="small" />
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}

function Journal({ dossier }: { dossier: DepositDetail }) {
  return (
    <Card variant="outlined">
      <CardHeader title="Journal" titleTypographyProps={{ variant: 'subtitle1', fontWeight: 700 }} />
      <CardContent sx={{ pt: 0, maxHeight: 360, overflowY: 'auto' }}>
        <Stack gap={1}>
          {dossier.activities.map((activity) => (
            <Box key={activity.id}>
              <Typography variant="body2">{activity.text}</Typography>
              <Typography variant="caption" color="text.secondary">
                {formatDateTime(activity.created_at)}
                {activity.user ? ` · ${activity.user}` : ''}
              </Typography>
            </Box>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}

function AbandonButton({ actions }: { actions: Actions }) {
  const fail = useFail();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  return (
    <>
      <Button color="error" size="small" onClick={() => setOpen(true)}>
        Abandonner ce renouvellement
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Abandonner ce renouvellement ?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Le dossier est clos et le pays est prévenu. L’AMM expirera à son échéance.
          </Typography>
          <TextField
            autoFocus
            fullWidth
            multiline
            label="Pourquoi ?"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Annuler</Button>
          <Button
            color="error"
            variant="contained"
            disabled={!reason.trim() || actions.abandon.isPending}
            onClick={() => actions.abandon.mutate(reason, { onSuccess: () => setOpen(false), onError: fail })}
          >
            Abandonner
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default function DepositDetailPage() {
  const { id = '' } = useParams();
  const query = useDeposit(id);
  const actions = useDepositActions(id);
  if (query.isPending) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} onRetry={() => query.refetch()} />;
  const dossier = query.data;
  const amm = dossier.amm;
  const done = stepsDone(dossier);
  const current = activeStep(dossier);
  const countryTodo = !dossier.can.manage && dossier.stage === 'ENVOYE';
  return (
    <Box>
      <Button component={Link} to="/depots" startIcon={<ArrowBackIcon />} size="small" sx={{ mb: 1 }}>
        Dépôts AMM
      </Button>
      <PageHeader
        title={
          <Stack direction="row" alignItems="center" gap={1.5}>
            <Flag iso2={amm.country_iso2} width={32} />
            <span>{amm.product_name}</span>
          </Stack>
        }
        subtitle={
          <>
            {amm.country_name} · renouvellement n°{dossier.renewal.sequence}
            {amm.original_number ? ` · AMM ${amm.original_number}` : ''} ·{' '}
            <MuiLink component={Link} to={`/amms/${amm.id}`}>
              fiche AMM
            </MuiLink>
          </>
        }
        actions={<StageChip stage={dossier.stage} label={dossier.stage_label} />}
      />
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} gap={{ xs: 1, md: 4 }} alignItems={{ md: 'center' }}>
          <Stack direction="row" gap={1} alignItems="center">
            <Typography variant="body2">
              Échéance de l’AMM : <strong>{formatDate(amm.effective_end_date)}</strong>
            </Typography>
            <StatusChip value={amm.status} />
          </Stack>
          <FilingDates ideal={amm.ideal_filing_date} agency={amm.agency_filing_deadline} />
          {dossier.renewal.filing_date && (
            <Typography variant="body2">
              Déposé le <strong>{formatDate(dossier.renewal.filing_date)}</strong>
            </Typography>
          )}
        </Stack>
        <Stepper activeStep={current} alternativeLabel sx={{ mt: 2 }} data-testid="deposit-stepper">
          {PROCEDURE.map((step, index) => (
            <Step key={step.title} completed={done[index]}>
              <StepLabel optional={<Typography variant="caption">{step.who}</Typography>}>
                {step.title}
              </StepLabel>
            </Step>
          ))}
        </Stepper>
      </Paper>
      {countryTodo && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <strong>À faire :</strong> télécharger le dossier, le déposer à {amm.authority || 'l’agence'} avec
          les échantillons, puis envoyer l’attestation de dépôt au siège (étape 4).
        </Alert>
      )}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <PiecesSection dossier={dossier} actions={actions} />
          <SamplesSection dossier={dossier} actions={actions} />
          <SendSection dossier={dossier} actions={actions} />
          <DepositSection dossier={dossier} actions={actions} />
          <FollowSection dossier={dossier} actions={actions} />
          <DecisionSection dossier={dossier} actions={actions} />
          {dossier.can.manage && (
            <Box sx={{ textAlign: 'right' }}>
              <AbandonButton actions={actions} />
            </Box>
          )}
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Messages dossier={dossier} actions={actions} />
          <Journal dossier={dossier} />
        </Grid>
      </Grid>
    </Box>
  );
}
