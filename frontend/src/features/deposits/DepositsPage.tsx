import { useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Collapse,
  Grid2 as Grid,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ChatBubbleOutlineIcon from '@mui/icons-material/ChatBubbleOutline';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import PlaylistAddCheckIcon from '@mui/icons-material/PlaylistAddCheck';
import { Link, useNavigate } from 'react-router';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { useDepositSuggestions, useDeposits, useOpenDeposit } from '@/api/hooks/useDeposits';
import type { DepositStage, DepositSummary } from '@/api/types';
import { isHqOrAdmin, useAuthStore } from '@/features/auth/authStore';
import { Flag } from '@/features/binders/Flag';
import { KpiCard } from '@/components/KpiCard';
import { PageHeader } from '@/components/PageHeader';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { StatusChip } from '@/components/chips';
import { filingDateText } from '@/components/FilingDates';
import { formatDate, formatDateTime, todayIso } from '@/lib/dates';
import { NewOriginDialog } from './NewOriginDialog';
import { CLOSED_STAGES, PROCEDURE, STAGE_COLORS, STAGE_STEP, isClosed } from './stages';

/** « renouvellement n°2 », ou « demande d'AMM d'origine » (1.4.1). */
export function dossierNature(dossier: DepositSummary, t: TFunction) {
  return dossier.renewal
    ? t('deposits.renewalNo', { n: dossier.renewal.sequence })
    : t('deposits.originApplication');
}

/** `key` : clé de texte `deposits.list.kpis.<key>.label` / `.hint`. */
const KPIS: { stages: DepositStage[]; key: string }[] = [
  { stages: ['MONTAGE'], key: 'assembly' },
  { stages: ['ENVOYE'], key: 'toSubmit' },
  { stages: ['DEPOSE'], key: 'submitted' },
  { stages: ['COMMISSION'], key: 'commission' },
  { stages: ['OBTENU'], key: 'granted' },
];

export function StageChip({ stage, label }: { stage: DepositStage; label: string }) {
  return (
    <Chip
      size="small"
      label={label}
      sx={{ bgcolor: STAGE_COLORS[stage], color: '#fff', fontWeight: 600 }}
      data-testid={`stage-${stage}`}
    />
  );
}

/** Six pastilles : où en est le dossier dans la procédure. */
function StageDots({ stage }: { stage: DepositStage }) {
  const { t } = useTranslation();
  const reached = STAGE_STEP[stage];
  return (
    <Stack direction="row" gap={0.5} aria-hidden>
      {PROCEDURE.map((step, index) => (
        <Tooltip key={step.key} title={t(`deposits.procedure.${step.key}.title`)}>
          <Box
            sx={{
              width: 10,
              height: 10,
              borderRadius: '50%',
              bgcolor: index < reached ? STAGE_COLORS[stage] : 'transparent',
              border: 2,
              borderColor: index <= reached ? STAGE_COLORS[stage] : 'divider',
            }}
          />
        </Tooltip>
      ))}
    </Stack>
  );
}

function Procedure() {
  const { t } = useTranslation();
  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardHeader
        title={t('deposits.list.procedureTitle')}
        subheader={t('deposits.list.procedureSubheader')}
        titleTypographyProps={{ variant: 'h6' }}
      />
      <CardContent sx={{ pt: 0 }}>
        <Stepper alternativeLabel nonLinear activeStep={-1}>
          {PROCEDURE.map((step) => (
            <Step key={step.key} completed={false}>
              <StepLabel
                optional={
                  <Typography variant="caption" color="text.secondary" component="div">
                    <strong>{t(`deposits.who.${step.who}`)}</strong> —{' '}
                    {t(`deposits.procedure.${step.key}.text`)}
                  </Typography>
                }
              >
                {t(`deposits.procedure.${step.key}.title`)}
              </StepLabel>
            </Step>
          ))}
        </Stepper>
      </CardContent>
    </Card>
  );
}

function DossierRow({ dossier }: { dossier: DepositSummary }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const amm = dossier.amm;
  const late =
    !dossier.filing_date && !!amm.agency_filing_deadline && amm.agency_filing_deadline < todayIso();
  return (
    <TableRow
      hover
      sx={{ cursor: 'pointer' }}
      onClick={() => navigate(`/depots/${dossier.id}`)}
      data-testid={`deposit-row-${dossier.id}`}
    >
      <TableCell>
        <Stack direction="row" alignItems="center" gap={1}>
          <Flag iso2={amm.country_iso2} width={22} />
          <Box>
            <Typography variant="body2" fontWeight={600}>
              {amm.product_name}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {amm.country_name} · {dossierNature(dossier, t)}
            </Typography>
          </Box>
        </Stack>
      </TableCell>
      <TableCell>
        <Stack gap={0.75}>
          <StageChip stage={dossier.stage} label={dossier.stage_label} />
          <StageDots stage={dossier.stage} />
        </Stack>
      </TableCell>
      <TableCell>
        {dossier.stage === 'MONTAGE' ? (
          <Box sx={{ minWidth: 110 }}>
            <Typography variant="caption">
              {t('deposits.list.progressPieces', {
                done: dossier.pieces_done,
                required: dossier.pieces_required,
              })}
              {dossier.samples_required && dossier.samples_count === 0
                ? t('deposits.list.progressSamples')
                : ''}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={dossier.pieces_required ? (100 * dossier.pieces_done) / dossier.pieces_required : 100}
            />
          </Box>
        ) : dossier.filing_date ? (
          <Typography variant="body2">
            {t('deposits.list.submittedOn', { date: formatDate(dossier.filing_date) })}
          </Typography>
        ) : (
          <Typography variant="body2">
            {t('deposits.list.sentOn', { date: formatDate(dossier.sent_at) })}
          </Typography>
        )}
      </TableCell>
      <TableCell>
        <Stack gap={0.5} alignItems="flex-start">
          <Typography variant="body2">{formatDate(amm.effective_end_date)}</Typography>
          <StatusChip value={amm.status} origin={amm.origin_application} />
        </Stack>
      </TableCell>
      <TableCell>
        <Typography variant="body2" color={late ? 'error' : undefined} fontWeight={late ? 600 : undefined}>
          {filingDateText(amm.agency_filing_deadline, t('deposits.overdue'))}
        </Typography>
      </TableCell>
      <TableCell>
        <Stack direction="row" alignItems="center" gap={1}>
          <Typography variant="caption" color="text.secondary">
            {formatDateTime(dossier.updated_at)}
          </Typography>
          {dossier.messages_count > 0 && (
            <Tooltip title={t('deposits.list.messagesCount', { n: dossier.messages_count })}>
              <Badge badgeContent={dossier.messages_count} color="primary">
                <ChatBubbleOutlineIcon fontSize="small" color="action" />
              </Badge>
            </Tooltip>
          )}
        </Stack>
      </TableCell>
    </TableRow>
  );
}

function Suggestions() {
  const suggestions = useDepositSuggestions();
  const open = useOpenDeposit();
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const { t } = useTranslation();
  const [showAll, setShowAll] = useState(false);
  if (suggestions.isPending) return <LoadingBlock minHeight={80} />;
  if (suggestions.isError) return <ErrorBlock error={suggestions.error} />;
  const rows = suggestions.data;
  if (rows.length === 0) return null;
  const visible = showAll ? rows : rows.slice(0, 8);
  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardHeader
        title={t('deposits.list.suggestionsTitle', { n: rows.length })}
        subheader={t('deposits.list.suggestionsSubheader')}
        titleTypographyProps={{ variant: 'h6' }}
      />
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('deposits.list.columns.product')}</TableCell>
              <TableCell>{t('deposits.list.columns.expiry')}</TableCell>
              <TableCell>{t('deposits.list.columns.agencyLimit')}</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {visible.map((amm) => (
              <TableRow key={amm.id}>
                <TableCell>
                  <Stack direction="row" alignItems="center" gap={1}>
                    <Flag iso2={amm.country_iso2} width={22} />
                    <Box>
                      <Typography variant="body2" fontWeight={600}>
                        {amm.product_name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {amm.country_name}
                        {amm.original_number ? t('deposits.ammNo', { number: amm.original_number }) : ''}
                      </Typography>
                    </Box>
                  </Stack>
                </TableCell>
                <TableCell>
                  <Stack direction="row" gap={1} alignItems="center">
                    {formatDate(amm.effective_end_date)} <StatusChip value={amm.status} />
                  </Stack>
                </TableCell>
                <TableCell>{filingDateText(amm.agency_filing_deadline, t('deposits.overdue'))}</TableCell>
                <TableCell align="right">
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={open.isPending}
                    onClick={() =>
                      open.mutate(amm.id, {
                        onSuccess: (dossier) => navigate(`/depots/${dossier.id}`),
                        onError: (error) => enqueueSnackbar(extractErrorMessage(error), { variant: 'error' }),
                      })
                    }
                  >
                    {t('deposits.list.buildDossier')}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      {rows.length > 8 && (
        <Box sx={{ p: 1, textAlign: 'center' }}>
          <Button size="small" onClick={() => setShowAll(!showAll)}>
            {showAll ? t('deposits.list.showLess') : t('deposits.list.showAll', { n: rows.length })}
          </Button>
        </Box>
      )}
    </Card>
  );
}

export default function DepositsPage() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const hq = isHqOrAdmin(user);
  const deposits = useDeposits();
  const [tab, setTab] = useState<'open' | 'closed'>('open');
  const [country, setCountry] = useState('');
  const [help, setHelp] = useState(false);
  const [newOrigin, setNewOrigin] = useState(false);

  const countries = useMemo(() => {
    const seen = new Map<string, string>();
    for (const dossier of deposits.data ?? []) seen.set(dossier.amm.country_iso2, dossier.amm.country_name);
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [deposits.data]);

  const all = deposits.data ?? [];
  const inCountry = all.filter((dossier) => !country || dossier.amm.country_iso2 === country);
  const rows = inCountry.filter((dossier) => (tab === 'open' ? !isClosed(dossier) : isClosed(dossier)));
  const toDeposit = all.filter((dossier) => dossier.stage === 'ENVOYE');

  return (
    <Box>
      <PageHeader
        title={t('nav.deposits')}
        subtitle={t('deposits.list.subtitle')}
        actions={
          <>
            <Button startIcon={<HelpOutlineIcon />} onClick={() => setHelp(!help)}>
              {t('deposits.list.procedureButton')}
            </Button>
            {hq && (
              <Button variant="contained" startIcon={<AddIcon />} onClick={() => setNewOrigin(true)}>
                {t('deposits.list.newOrigin')}
              </Button>
            )}
            {hq && (
              <Button
                component={Link}
                to="/depots/pieces"
                variant="outlined"
                startIcon={<PlaylistAddCheckIcon />}
              >
                {t('deposits.list.piecesButton')}
              </Button>
            )}
          </>
        }
      />
      {hq && <NewOriginDialog open={newOrigin} onClose={() => setNewOrigin(false)} />}
      <Collapse in={help}>
        <Procedure />
      </Collapse>
      {!hq && toDeposit.length > 0 && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('deposits.list.toSubmitAlert', { count: toDeposit.length })}
        </Alert>
      )}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {KPIS.map((kpi) => (
          <Grid key={kpi.key} size={{ xs: 6, sm: 4, md: 2.4 }}>
            <KpiCard
              label={t(`deposits.list.kpis.${kpi.key}.label`)}
              hint={t(`deposits.list.kpis.${kpi.key}.hint`)}
              value={deposits.data ? inCountry.filter((d) => kpi.stages.includes(d.stage)).length : '—'}
              color={STAGE_COLORS[kpi.stages[0]]}
            />
          </Grid>
        ))}
      </Grid>
      {hq && <Suggestions />}
      <Paper variant="outlined">
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 2,
            px: 2,
            borderBottom: 1,
            borderColor: 'divider',
            flexWrap: 'wrap',
          }}
        >
          <Tabs value={tab} onChange={(_e, value) => setTab(value)} sx={{ flexGrow: 1 }}>
            <Tab
              value="open"
              label={t('deposits.list.tabOpen', { n: inCountry.filter((d) => !isClosed(d)).length })}
            />
            <Tab
              value="closed"
              label={t('deposits.list.tabClosed', {
                n: inCountry.filter((d) => CLOSED_STAGES.includes(d.stage)).length,
              })}
            />
          </Tabs>
          {countries.length > 1 && (
            <TextField
              select
              size="small"
              label={t('deposits.list.country')}
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              sx={{ minWidth: 180, my: 1 }}
            >
              <MenuItem value="">{t('deposits.list.allCountries')}</MenuItem>
              {countries.map(([iso2, name]) => (
                <MenuItem key={iso2} value={iso2}>
                  {name}
                </MenuItem>
              ))}
            </TextField>
          )}
        </Box>
        {deposits.isPending && <LoadingBlock />}
        {deposits.isError && <ErrorBlock error={deposits.error} onRetry={() => deposits.refetch()} />}
        {deposits.data && rows.length === 0 && (
          <EmptyBlock
            text={
              tab === 'open'
                ? hq
                  ? t('deposits.list.emptyOpenHq')
                  : t('deposits.list.emptyOpenCountry')
                : t('deposits.list.emptyClosed')
            }
          />
        )}
        {rows.length > 0 && (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('deposits.list.columns.product')}</TableCell>
                  <TableCell>{t('deposits.list.columns.stage')}</TableCell>
                  <TableCell>{t('deposits.list.columns.progress')}</TableCell>
                  <TableCell>{t('deposits.list.columns.ammExpiry')}</TableCell>
                  <TableCell>{t('deposits.list.columns.agencyLimit')}</TableCell>
                  <TableCell>{t('deposits.list.columns.lastActivity')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((dossier) => (
                  <DossierRow key={dossier.id} dossier={dossier} />
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
    </Box>
  );
}
