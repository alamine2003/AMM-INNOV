import { useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  AlertTitle,
  Autocomplete,
  Box,
  Button,
  Chip,
  LinearProgress,
  Link as MuiLink,
  Paper,
  Stack,
  Step,
  StepContent,
  StepLabel,
  Stepper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Link, useParams, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { extractErrorMessage } from '@/api/client';
import { useAmms } from '@/api/hooks/useAmms';
import {
  useAnalyzeDossier,
  useChooseAmm,
  useConfirmDossier,
  useDossierImport,
} from '@/api/hooks/useDossierImports';
import { useCountries } from '@/api/hooks/useCatalog';
import { canEditCountry, isHqOrAdmin, useAuthStore } from '@/features/auth/authStore';
import {
  hasSummary,
  type Amm,
  type AmmStatus,
  type DossierImportBatch,
  type DossierImportFile,
  type DossierState,
} from '@/api/types';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { PageHeader } from '@/components/PageHeader';
import { BinderLink } from '@/features/binders/BinderLink';
import { FilingDates } from '@/components/FilingDates';
import { DossierChip, StatusChip } from '@/components/chips';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { formatDate, formatDateTime } from '@/lib/dates';
import i18n from '@/lib/i18n';
import { DossierFileViewer } from './DossierFileViewer';
import { DossierImportSummaryCard } from './DossierImportSummaryCard';
import { ReviewPointsList } from './ReviewPointsList';
import {
  batchState,
  buildTimeline,
  documentKindLabel,
  fieldLabel,
  humanize,
  periodTitle,
  showValue,
  stateSentence,
} from './dossierReview';

const fileName = (path: string) => path.split('/').at(-1) ?? path;
/** « AMM groupée 23 DEC 2023.pdf (p. 3-4) » : la partie du recueil qui concerne le produit. */
const scanName = (doc: { path: string; pages?: [number, number] | null }) =>
  fileName(doc.path) +
  (doc.pages
    ? ` ${i18n.t('dossierImports.detail.pages', { pages: doc.pages[0] === doc.pages[1] ? doc.pages[0] : `${doc.pages[0]}-${doc.pages[1]}` })}`
    : '');
const period = (start: string | null, end: string | null) =>
  `${formatDate(start, i18n.t('dossierImports.detail.dateNotRead'))} → ${formatDate(end, i18n.t('dossierImports.detail.dateNotRead'))}`;

/** La seule question que pose l'import : à quelle AMM ranger ces documents ? */
function AmmQuestion({ batch }: { batch: DossierImportBatch }) {
  const { t } = useTranslation();
  const preview = batch.preview!;
  const question = preview.question;
  const user = useAuthStore((s) => s.user);
  // Pré-rempli avec la marque lue sur les décisions ; la liste montre les AMM du pays.
  const brand = preview.amm.product_name.split(' ')[0] ?? '';
  const [input, setInput] = useState(brand);
  const [search, setSearch] = useState(brand);
  const [chosen, setChosen] = useState<Amm | null>(null);
  const [creating, setCreating] = useState(false);
  // Limité au pays du dossier quand il est connu ; l'API limite déjà au périmètre de l'utilisateur.
  const amms = useAmms({ search, country: preview.amm.country_iso2 || undefined, page: 1 });
  const choose = useChooseAmm(batch.id);
  const confirm = useConfirmDossier(batch.id);
  const isGlobal = isHqOrAdmin(user);
  const results = amms.data?.results ?? [];
  const options = chosen && !results.some((amm) => amm.id === chosen.id) ? [chosen, ...results] : results;
  return (
    <Paper
      variant="outlined"
      sx={{ p: 3 }}
      component="section"
      aria-label={t('dossierImports.detail.questionAria')}
    >
      <Typography variant="h6" gutterBottom>
        {t('dossierImports.detail.questionTitle')}
      </Typography>
      {question && question.reasons.length > 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {question.reasons.map((reason) => humanize(reason, preview)).join(' ')}
        </Typography>
      )}
      <Stack direction={{ xs: 'column', sm: 'row' }} gap={2} alignItems={{ sm: 'center' }}>
        <Autocomplete
          sx={{ minWidth: 320, flex: 1 }}
          options={options}
          value={chosen}
          loading={amms.isFetching}
          filterOptions={(items) => items}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          getOptionLabel={(amm) =>
            `${t('dossierImports.detail.optionLabel', { product: amm.product_name, country: amm.country_name })}${amm.original_number ? t('dossierImports.detail.optionNumber', { number: amm.original_number }) : ''}`
          }
          onChange={(_, value) => setChosen(value)}
          inputValue={input}
          onInputChange={(_, value, reason) => {
            setInput(value);
            if (reason === 'input') setSearch(value);
          }}
          noOptionsText={t('dossierImports.detail.noOptions')}
          renderInput={(params) => (
            <TextField
              {...params}
              label={t('dossierImports.detail.searchLabel')}
              helperText={
                preview.amm.country_iso2
                  ? t('dossierImports.detail.helperCountry', { country: preview.amm.country_iso2 })
                  : t('dossierImports.detail.helperScope')
              }
            />
          )}
        />
        <Button
          variant="contained"
          size="large"
          disabled={!chosen || choose.isPending}
          onClick={() => chosen && choose.mutate(chosen.id)}
        >
          {t('dossierImports.detail.fileHere')}
        </Button>
      </Stack>
      {choose.isError && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {extractErrorMessage(choose.error)}
        </Alert>
      )}
      {isGlobal && question?.can_create && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="body2" color="text.secondary">
            {t('dossierImports.detail.createIntro')}
          </Typography>
          <Button size="small" sx={{ mt: 1 }} onClick={() => setCreating(true)} disabled={confirm.isPending}>
            {t('dossierImports.detail.createButton', {
              product: preview.amm.product_name,
              country: preview.amm.country_iso2,
            })}
          </Button>
          {confirm.isError && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {extractErrorMessage(confirm.error)}
            </Alert>
          )}
          <ConfirmDialog
            open={creating}
            title={t('dossierImports.detail.createTitle')}
            text={t('dossierImports.detail.createText', {
              product: preview.amm.product_name,
              country: preview.amm.country_iso2,
            })}
            confirmColor="primary"
            loading={confirm.isPending}
            onClose={() => setCreating(false)}
            onConfirm={() => {
              setCreating(false);
              confirm.mutate({ preview_token: batch.preview_token, create_amm: true });
            }}
          />
        </Box>
      )}
    </Paper>
  );
}

/** Statut, échéance et complétude de l'AMM après rangement (ou prévus avant). */
function Result({ batch }: { batch: DossierImportBatch }) {
  const { t } = useTranslation();
  const summary = hasSummary(batch.summary) ? batch.summary : null;
  const projection = batch.preview?.projection;
  const state = summary
    ? {
        status: summary.after.status,
        dossier: summary.after.dossier_state,
        end: summary.after.effective_end_date,
        missing: summary.missing_scan,
      }
    : projection
      ? {
          status: projection.status,
          dossier: projection.dossier_state,
          end: projection.effective_end_date,
          missing: projection.missing_scan,
        }
      : null;
  if (!state) return null;
  const applied = batch.status === 'APPLIED';
  return (
    <Paper
      variant="outlined"
      sx={{ p: 3 }}
      component="section"
      aria-label={t('dossierImports.detail.resultAria')}
    >
      <Typography variant="h6" gutterBottom>
        {applied ? t('dossierImports.detail.resultTitle') : t('dossierImports.detail.resultTitlePlanned')}
      </Typography>
      <Stack spacing={1}>
        <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
          <Typography>{t('dossierImports.detail.statusLabel')}</Typography>
          <StatusChip value={state.status as AmmStatus} />
          <DossierChip value={state.dossier as DossierState} />
        </Stack>
        <Typography>
          {t('dossierImports.detail.expiryLabel')}{' '}
          <strong>{formatDate(state.end, t('dossierImports.detail.expiryUnknown'))}</strong>
        </Typography>
        {projection && !applied && state.end && (
          <FilingDates ideal={projection.ideal_filing_date} agency={projection.agency_filing_deadline} />
        )}
        <Typography>
          {state.dossier === 'COMPLET'
            ? t('dossierImports.detail.dossierComplete')
            : t('dossierImports.detail.dossierIncomplete', {
                scan: state.missing ?? t('dossierImports.detail.missingDefault'),
              })}
        </Typography>
      </Stack>
    </Paper>
  );
}

function BatchContent({ batch }: { batch: DossierImportBatch }) {
  const { t } = useTranslation();
  const preview = batch.preview;
  const [search] = useSearchParams();
  const [viewing, setViewing] = useState<DossierImportFile | null>(
    () => batch.files.find((file) => file.id === search.get('file')) ?? null,
  );
  const user = useAuthStore((s) => s.user);
  const countries = useCountries();
  const confirm = useConfirmDossier(batch.id);
  const analyze = useAnalyzeDossier(batch.id);
  const applied = batch.status === 'APPLIED';
  const question = batch.status === 'QUESTION';
  const view = (fileId: string | null) => setViewing(batch.files.find((file) => file.id === fileId) ?? null);
  const { steps, otherDocuments } = preview ? buildTimeline(preview) : { steps: [], otherDocuments: [] };
  const countryName =
    (countries.data ?? []).find((c) => c.iso2 === preview?.amm.country_iso2)?.name ??
    preview?.amm.country_iso2;
  const ammId = batch.amm_id ?? preview?.amm.id;
  const editable = canEditCountry(user, preview?.amm.country_iso2);
  const planned = preview?.review_points ?? [];
  const legacy = (preview?.version ?? 1) < 2;

  return (
    <Stack spacing={3}>
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h5" component="h2" data-testid="batch-state">
          {stateSentence(batch)}
        </Typography>
        {preview && !question && (
          <Typography variant="body1" sx={{ mt: 1 }}>
            {ammId ? (
              <MuiLink component={Link} to={`/amms/${ammId}`}>
                {preview.amm.product_name || t('dossierImports.detail.ma')}
              </MuiLink>
            ) : (
              preview.amm.product_name
            )}
            {countryName ? ` · ${countryName}` : ''}
          </Typography>
        )}
        {applied && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {t('dossierImports.detail.appliedNote')}
          </Typography>
        )}
        {batch.status === 'READY' && (
          <Stack direction="row" gap={2} alignItems="center" sx={{ mt: 2 }} flexWrap="wrap">
            {legacy ? (
              // Lot lu avant le rangement automatique : une nouvelle lecture le range d'elle-même.
              <Button
                variant="contained"
                size="large"
                disabled={analyze.isPending}
                onClick={() => analyze.mutate({})}
              >
                {t('dossierImports.detail.rereadAndFile')}
              </Button>
            ) : (
              <Button
                variant="contained"
                size="large"
                disabled={confirm.isPending || !batch.preview_token}
                onClick={() => confirm.mutate({ preview_token: batch.preview_token })}
              >
                {confirm.isPending
                  ? t('dossierImports.detail.filing')
                  : t('dossierImports.detail.fileDocuments')}
              </Button>
            )}
            <Typography variant="body2" color="text.secondary">
              {legacy
                ? t('dossierImports.detail.legacyNote')
                : batch.status_reason || t('dossierImports.detail.identifiedNoFiling')}
            </Typography>
          </Stack>
        )}
        {confirm.isError && !question && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {axiosStatus(confirm.error) === 409
              ? t('dossierImports.detail.conflict')
              : extractErrorMessage(confirm.error)}
          </Alert>
        )}
      </Paper>

      {batch.status === 'FAILED' && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" disabled={analyze.isPending} onClick={() => analyze.mutate({})}>
              {t('dossierImports.detail.rerun')}
            </Button>
          }
        >
          {batch.error || t('dossierImports.detail.failedFallback')}
        </Alert>
      )}

      {question && <AmmQuestion batch={batch} />}

      {preview && !question && (
        <Box>
          <Typography variant="h6" gutterBottom>
            {t('dossierImports.detail.timelineTitle')}
          </Typography>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stepper
              orientation="vertical"
              nonLinear
              activeStep={-1}
              aria-label={t('dossierImports.detail.timelineAria')}
            >
              {steps.map((step, index) => (
                <Step key={step.id} active expanded completed={false} data-testid={`step-${index + 1}`}>
                  <StepLabel icon={index + 1}>
                    <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
                      <Typography fontWeight={600}>{step.title}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {period(step.start, step.end)}
                      </Typography>
                      {step.isNew && (
                        <Chip
                          size="small"
                          color="primary"
                          variant="outlined"
                          label={
                            applied
                              ? t('dossierImports.detail.addedByThis')
                              : t('dossierImports.detail.willBeAdded')
                          }
                        />
                      )}
                      {step.inForce && (
                        <Chip
                          size="small"
                          color="success"
                          variant="outlined"
                          label={t('dossierImports.detail.inForce')}
                        />
                      )}
                    </Stack>
                  </StepLabel>
                  <StepContent>
                    <Stack spacing={1}>
                      {step.number && (
                        <Typography variant="body2">
                          {t('dossierImports.detail.numberLine', { number: step.number })}
                        </Typography>
                      )}
                      {step.scans.map((doc) => (
                        <Stack key={doc.file_id} direction="row" alignItems="center" gap={1} flexWrap="wrap">
                          <Button size="small" variant="outlined" onClick={() => view(doc.file_id)}>
                            {t('dossierImports.viewScan')}
                          </Button>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ overflowWrap: 'anywhere' }}
                          >
                            {scanName(doc)}
                            {doc.duplicate_id ? ` · ${t('dossierImports.detail.alreadyInRecord')}` : ''}
                          </Typography>
                        </Stack>
                      ))}
                      {!step.scans.length && (
                        <Typography variant="caption" color="text.secondary">
                          {step.inDossier
                            ? t('dossierImports.detail.noDecisionScan')
                            : t('dossierImports.detail.alreadyRecorded')}
                        </Typography>
                      )}
                    </Stack>
                  </StepContent>
                </Step>
              ))}
            </Stepper>
          </Paper>
        </Box>
      )}

      {!question && <Result batch={batch} />}

      {applied && batch.review_points && batch.review_points.length > 0 && (
        <ReviewPointsList points={batch.review_points} editable={editable} />
      )}
      {batch.status === 'READY' && planned.length > 0 && (
        <Paper
          variant="outlined"
          sx={{ p: 3 }}
          component="section"
          aria-label={t('dossierImports.reviewPoints.ariaLabel')}
        >
          <Typography variant="h6">
            {t('dossierImports.reviewPoints.title', { count: planned.length })}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {t('dossierImports.detail.plannedNote')}
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 2 }}>
            {planned.map((point, index) => (
              <li key={index}>
                <Typography variant="body2">{humanize(point.message, preview!)}</Typography>
              </li>
            ))}
          </Box>
        </Paper>
      )}

      {preview && !question && otherDocuments.length > 0 && (
        <Accordion variant="outlined" disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>
              {t('dossierImports.detail.otherDocuments', { count: otherDocuments.length })}
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={1}>
              {otherDocuments.map((doc) => (
                <Stack key={doc.file_id} direction="row" alignItems="center" gap={1} flexWrap="wrap">
                  <Button size="small" onClick={() => view(doc.file_id)}>
                    {t('dossierImports.viewScan')}
                  </Button>
                  <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>
                    {scanName(doc)}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {documentKindLabel(doc.kind)} · {periodTitle(doc.period, preview)}
                    {doc.duplicate_id ? ` · ${t('dossierImports.detail.alreadyInRecord')}` : ''}
                  </Typography>
                </Stack>
              ))}
            </Stack>
          </AccordionDetails>
        </Accordion>
      )}

      <Accordion variant="outlined" disableGutters>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography>{t('dossierImports.detail.readingDetails')}</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack spacing={2}>
            {preview && (
              <Typography variant="body2" color="text.secondary">
                {t('dossierImports.detail.confidence', { confidence: preview.confidence })}
              </Typography>
            )}
            {preview?.ignored && preview.ignored.length > 0 && (
              <Box>
                <Typography variant="body2" color="text.secondary">
                  {t('dossierImports.detail.ignoredDocs')}
                </Typography>
                <Box component="ul" sx={{ m: 0, pl: 2 }}>
                  {preview.ignored.map((item) => (
                    <li key={item.file_id}>
                      <Typography variant="caption">{fileName(item.path)}</Typography>
                      <Button size="small" onClick={() => view(item.file_id)}>
                        {t('dossierImports.viewScan')}
                      </Button>
                    </li>
                  ))}
                </Box>
              </Box>
            )}
            {preview && preview.warnings.length > 0 && (
              <Box component="ul" sx={{ m: 0, pl: 2 }}>
                {preview.warnings.map((line, index) => (
                  <li key={index}>
                    <Typography variant="caption">{humanize(line, preview)}</Typography>
                  </li>
                ))}
              </Box>
            )}
            {hasSummary(batch.summary) && <DossierImportSummaryCard summary={batch.summary} />}
            {batch.audit.length > 0 && (
              <TableContainer>
                <Table size="small" aria-label={t('dossierImports.detail.auditAria')}>
                  <TableHead>
                    <TableRow>
                      <TableCell>{t('dossierImports.columns.information')}</TableCell>
                      <TableCell>{t('dossierImports.columns.before')}</TableCell>
                      <TableCell>{t('dossierImports.columns.after')}</TableCell>
                      <TableCell>{t('dossierImports.columns.by')}</TableCell>
                      <TableCell>{t('dossierImports.columns.proof')}</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {batch.audit.map((entry) => (
                      <TableRow key={entry.id}>
                        <TableCell>
                          {fieldLabel(entry.field)}
                          <Typography variant="caption" display="block">
                            {entry.target === 'amm'
                              ? t('dossierImports.period.original')
                              : t('dossierImports.detail.renewal')}
                          </Typography>
                        </TableCell>
                        <TableCell sx={{ overflowWrap: 'anywhere' }}>
                          {showValue(entry.field, entry.old_value)}
                        </TableCell>
                        <TableCell sx={{ overflowWrap: 'anywhere' }}>
                          {showValue(entry.field, entry.new_value)}
                        </TableCell>
                        <TableCell>
                          {entry.user_email}
                          <Typography variant="caption" display="block">
                            {formatDateTime(entry.created_at)}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Button size="small" onClick={() => view(entry.proof_file_id)}>
                            {t('dossierImports.viewScan')}
                          </Button>
                          <Typography variant="caption" display="block">
                            {entry.reason}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
            {!applied && batch.status !== 'FAILED' && (
              <Box>
                <Button variant="outlined" disabled={analyze.isPending} onClick={() => analyze.mutate({})}>
                  {t('dossierImports.detail.rerun')}
                </Button>
              </Box>
            )}
            {analyze.isError && <Alert severity="error">{extractErrorMessage(analyze.error)}</Alert>}
          </Stack>
        </AccordionDetails>
      </Accordion>
      <DossierFileViewer batchId={batch.id} file={viewing} onClose={() => setViewing(null)} />
    </Stack>
  );
}

function axiosStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null)?.response?.status;
}

export default function DossierImportDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const query = useDossierImport(id);
  if (query.isPending) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} onRetry={() => query.refetch()} />;
  const batch = query.data;
  const running = ['PENDING', 'RUNNING'].includes(batch.status);
  const state = batchState(batch);
  return (
    <Box>
      <PageHeader
        title={batch.root_name}
        subtitle={t('dossierImports.detail.subtitle', { date: formatDateTime(batch.created_at) })}
        actions={
          <>
            <Chip label={state.label} color={state.tone} />
            {batch.status === 'APPLIED' && <BinderLink ammId={batch.amm_id} />}
            <Button component={Link} to="/dossier-imports">
              {t('dossierImports.detail.allImports')}
            </Button>
          </>
        }
      />
      {running ? (
        <Stack spacing={2}>
          <Alert severity="info">
            <AlertTitle>{t('dossierImports.sentence.running')}</AlertTitle>
            {t('dossierImports.detail.runningBody')}
          </Alert>
          <LinearProgress />
        </Stack>
      ) : (
        <BatchContent key={`${batch.id}-${batch.preview_token}-${batch.status}`} batch={batch} />
      )}
    </Box>
  );
}
