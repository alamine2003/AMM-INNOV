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
import { Link, useNavigate, useParams } from 'react-router';
import { useSnackbar } from 'notistack';
import { useTranslation } from 'react-i18next';
import { useDeposit, useDepositActions } from '@/api/hooks/useDeposits';
import type { DepositDetail } from '@/api/types';
import { Flag } from '@/features/binders/Flag';
import { FilingDates } from '@/components/FilingDates';
import { PageHeader } from '@/components/PageHeader';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { StatusChip } from '@/components/chips';
import { formatDate, formatDateTime } from '@/lib/dates';
import { StageChip, dossierNature } from './DepositsPage';
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
  const { t } = useTranslation();
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
        title={t('deposits.detail.messagesTitle')}
        subheader={t('deposits.detail.messagesSubheader')}
        titleTypographyProps={{ variant: 'subtitle1', fontWeight: 700 }}
      />
      <CardContent sx={{ pt: 0 }}>
        <Box sx={{ maxHeight: 380, overflowY: 'auto', mb: 1.5, pr: 0.5 }} data-testid="messages">
          {dossier.messages.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              {t('deposits.detail.noMessage')}
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
                  <strong>{message.author ?? '?'}</strong> ·{' '}
                  {message.from_hq ? t('deposits.who.hq') : t('deposits.who.country')} ·{' '}
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
            label={t('deposits.detail.yourMessage')}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit();
            }}
          />
          <Button
            variant="contained"
            aria-label={t('deposits.detail.sendMessage')}
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
  const { t } = useTranslation();
  return (
    <Card variant="outlined">
      <CardHeader
        title={t('deposits.detail.log')}
        titleTypographyProps={{ variant: 'subtitle1', fontWeight: 700 }}
      />
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

function AbandonButton({ actions, origin }: { actions: Actions; origin: boolean }) {
  const fail = useFail();
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  return (
    <>
      <Button color="error" size="small" onClick={() => setOpen(true)}>
        {t(origin ? 'deposits.detail.abandonOrigin' : 'deposits.detail.abandonButton')}
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {t(origin ? 'deposits.detail.abandonOriginTitle' : 'deposits.detail.abandonTitle')}
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            {t(origin ? 'deposits.detail.abandonOriginText' : 'deposits.detail.abandonText')}
          </Typography>
          <TextField
            autoFocus
            fullWidth
            multiline
            label={t('deposits.detail.abandonReason')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('app.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={!reason.trim() || actions.abandon.isPending}
            onClick={() => actions.abandon.mutate(reason, { onSuccess: () => setOpen(false), onError: fail })}
          >
            {t('deposits.detail.abandonConfirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

/** Annuler le dossier ouvert par erreur : tout part à la corbeille (1.4.1). */
function CancelButton({ actions }: { actions: Actions }) {
  const fail = useFail();
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  return (
    <>
      <Button color="inherit" size="small" onClick={() => setOpen(true)}>
        {t('deposits.detail.cancelButton')}
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('deposits.detail.cancelTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            {t('deposits.detail.cancelText')}
          </Typography>
          <TextField
            autoFocus
            fullWidth
            multiline
            label={t('deposits.detail.cancelReason')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('app.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={actions.cancel.isPending}
            onClick={() =>
              actions.cancel.mutate(reason.trim(), {
                onSuccess: () => {
                  enqueueSnackbar(t('deposits.detail.cancelled'), { variant: 'success' });
                  navigate('/depots');
                },
                onError: fail,
              })
            }
          >
            {t('deposits.detail.cancelConfirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default function DepositDetailPage() {
  const { id = '' } = useParams();
  const { t } = useTranslation();
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
        {t('nav.deposits')}
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
            {amm.country_name} · {dossierNature(dossier, t)}
            {amm.original_number ? t('deposits.ammNo', { number: amm.original_number }) : ''} ·{' '}
            <MuiLink component={Link} to={`/amms/${amm.id}`}>
              {t('deposits.detail.maRecord')}
            </MuiLink>
          </>
        }
        actions={<StageChip stage={dossier.stage} label={dossier.stage_label} />}
      />
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} gap={{ xs: 1, md: 4 }} alignItems={{ md: 'center' }}>
          {dossier.renewal ? (
            <>
              <Stack direction="row" gap={1} alignItems="center">
                <Typography variant="body2">
                  {t('deposits.detail.maExpiryLabel')}
                  <strong>{formatDate(amm.effective_end_date)}</strong>
                </Typography>
                <StatusChip value={amm.status} origin={amm.origin_application} />
              </Stack>
              <FilingDates ideal={amm.ideal_filing_date} agency={amm.agency_filing_deadline} />
            </>
          ) : (
            <Stack direction="row" gap={1} alignItems="center">
              <StatusChip value={amm.status} origin={amm.origin_application} />
              <Typography variant="body2" color="text.secondary">
                {amm.original_number
                  ? t('deposits.ammNo', { number: amm.original_number })
                  : t('deposits.detail.noMaYet')}
              </Typography>
            </Stack>
          )}
          {dossier.filing_date && (
            <Typography variant="body2">
              {t('deposits.detail.submittedOnLabel')}
              <strong>{formatDate(dossier.filing_date)}</strong>
            </Typography>
          )}
        </Stack>
        <Stepper activeStep={current} alternativeLabel sx={{ mt: 2 }} data-testid="deposit-stepper">
          {PROCEDURE.map((step, index) => (
            <Step key={step.key} completed={done[index]}>
              <StepLabel
                optional={<Typography variant="caption">{t(`deposits.who.${step.who}`)}</Typography>}
              >
                {t(`deposits.procedure.${step.key}.title`)}
              </StepLabel>
            </Step>
          ))}
        </Stepper>
      </Paper>
      {countryTodo && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <strong>{t('deposits.detail.todoLabel')}</strong>{' '}
          {t('deposits.detail.todoText', { authority: amm.authority || t('deposits.defaultAgency') })}
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
          {(dossier.can.manage || dossier.can.cancel) && (
            <Stack direction="row" justifyContent="flex-end" gap={1}>
              {dossier.can.cancel && <CancelButton actions={actions} />}
              {dossier.can.manage && <AbandonButton actions={actions} origin={!dossier.renewal} />}
            </Stack>
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
