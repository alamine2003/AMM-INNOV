import { useState } from 'react';
import axios from 'axios';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  AlertTitle,
  Box,
  Button,
  Chip,
  LinearProgress,
  Link as MuiLink,
  MenuItem,
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
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Link, useParams, useSearchParams } from 'react-router';
import { extractErrorMessage } from '@/api/client';
import { useAnalyzeDossier, useConfirmDossier, useDossierImport } from '@/api/hooks/useDossierImports';
import { useCountries } from '@/api/hooks/useCatalog';
import { useAuthStore } from '@/features/auth/authStore';
import {
  hasSummary,
  type DossierImportBatch,
  type DossierImportChange,
  type DossierImportFile,
} from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { formatDate, formatDateTime } from '@/lib/dates';
import { DossierFileViewer } from './DossierFileViewer';
import { DossierImportSummaryCard } from './DossierImportSummaryCard';
import {
  actionLabels,
  ammStatusLabels,
  batchState,
  blockingReasons,
  buildTimeline,
  documentKindLabels,
  fieldLabels,
  isBlocked,
  periodTitle,
  reviewPoints,
  showValue,
  stateSentence,
  type StepAction,
  type TimelineStep,
} from './dossierReview';

const actionColors: Record<StepAction, 'default' | 'primary' | 'info' | 'warning'> = {
  recorded: 'default',
  added: 'primary',
  completed: 'info',
  review: 'warning',
};
const fileName = (path: string) => path.split('/').at(-1) ?? path;
const period = (start: string | null, end: string | null) =>
  `${formatDate(start, 'date non lue')} → ${formatDate(end, 'date non lue')}`;

/** Choix explicite entre la valeur enregistrée et celle lue sur le scan ; « Garder » par défaut. */
function ChangeChoice({
  change,
  stepTitle,
  replace,
  disabled,
  onChange,
  onView,
}: {
  change: DossierImportChange;
  stepTitle: string;
  replace: boolean;
  disabled: boolean;
  onChange: (replace: boolean) => void;
  onView: () => void;
}) {
  const label = fieldLabels[change.field] ?? change.field;
  return (
    <Box data-testid={`change-${change.id}`} sx={{ py: 1 }}>
      <Typography variant="subtitle2">{label} : le scan ne dit pas la même chose que la fiche</Typography>
      <ToggleButtonGroup
        exclusive
        size="small"
        color="primary"
        value={replace ? 'replace' : 'keep'}
        disabled={disabled}
        onChange={(_, value: 'keep' | 'replace' | null) => value && onChange(value === 'replace')}
        aria-label={`${label} — ${stepTitle}`}
        sx={{ flexWrap: 'wrap', my: 0.5 }}
      >
        <ToggleButton value="keep" sx={{ textTransform: 'none' }}>
          Garder : {showValue(change.field, change.old)} (enregistré)
        </ToggleButton>
        <ToggleButton value="replace" sx={{ textTransform: 'none' }}>
          Remplacer par : {showValue(change.field, change.new)} (lu sur le scan, {change.confidence} %)
        </ToggleButton>
      </ToggleButtonGroup>
      {change.confidence < 90 && (
        <Alert severity="warning" sx={{ py: 0 }} action={<Button onClick={onView}>Voir le scan</Button>}>
          Lecture incertaine, vérifiez sur le scan.
        </Alert>
      )}
    </Box>
  );
}

function TimelineStepContent({
  step,
  applied,
  replaced,
  disabled,
  onChoice,
  view,
}: {
  step: TimelineStep;
  applied: boolean;
  replaced: string[];
  disabled: boolean;
  onChoice: (id: string, replace: boolean) => void;
  view: (fileId: string | null) => void;
}) {
  return (
    <Stack spacing={1}>
      {step.number && <Typography variant="body2">N° {step.number}</Typography>}
      {step.scans.map((doc) => (
        <Stack key={doc.file_id} direction="row" alignItems="center" gap={1} flexWrap="wrap">
          <Button size="small" variant="outlined" onClick={() => view(doc.file_id)}>
            Voir le scan
          </Button>
          <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
            {fileName(doc.path)}
            {doc.duplicate_id ? ' · déjà présent dans la fiche' : ''}
          </Typography>
        </Stack>
      ))}
      {!step.scans.length && (
        <Typography variant="caption" color="text.secondary">
          {step.inDossier
            ? 'Aucun scan de la décision dans ce dossier.'
            : 'Enregistré dans la fiche ; aucun document de ce dossier ne le concerne.'}
        </Typography>
      )}
      {step.confidence !== null && step.confidence < 90 && !step.choices.length && !applied && (
        <Typography variant="caption" color="warning.main">
          Lecture incertaine ({step.confidence} %), vérifiez sur le scan.
        </Typography>
      )}
      {!applied &&
        step.completions.map((change) => (
          <Typography key={change.id} variant="body2" data-testid={`change-${change.id}`}>
            Sera complété : {fieldLabels[change.field] ?? change.field} →{' '}
            {showValue(change.field, change.new)}
          </Typography>
        ))}
      {!applied &&
        step.choices.map((change) => (
          <ChangeChoice
            key={change.id}
            change={change}
            stepTitle={step.title}
            replace={replaced.includes(change.id)}
            disabled={disabled}
            onChange={(replace) => onChoice(change.id, replace)}
            onView={() => view(change.proof_file_id)}
          />
        ))}
    </Stack>
  );
}

function PreviewContent({ batch }: { batch: DossierImportBatch }) {
  const preview = batch.preview;
  const [search] = useSearchParams();
  const [viewing, setViewing] = useState<DossierImportFile | null>(
    () => batch.files.find((file) => file.id === search.get('file')) ?? null,
  );
  // Corrections pour lesquelles « Remplacer » est choisi : c'est exactement `accepted_changes`.
  const [replaced, setReplaced] = useState<string[]>([]);
  // Pays imposé pour la ré-analyse quand les documents ne le nomment pas (scan illisible, décision
  // sans en-tête) ; limité au périmètre de l'utilisateur.
  const [country, setCountry] = useState(preview?.amm.country_iso2 ?? '');
  const user = useAuthStore((s) => s.user);
  const countries = useCountries();
  const allowedCountries = (countries.data ?? []).filter(
    (c) => user?.role !== 'COUNTRY_REGULATORY' || user.countries.includes(c.iso2),
  );
  // Tant que le catalogue n'est pas chargé — ou si le pays détecté est hors périmètre — la
  // valeur n'a pas d'option correspondante : on affiche et on envoie « détection automatique ».
  const selectedCountry = allowedCountries.some((c) => c.iso2 === country) ? country : '';
  const confirm = useConfirmDossier(batch.id);
  const analyze = useAnalyzeDossier(batch.id);
  const stale = axios.isAxiosError(confirm.error) && confirm.error.response?.status === 409;
  const busy = confirm.isPending || analyze.isPending;
  const applied = batch.status === 'APPLIED';
  const blocked = isBlocked(preview);
  const view = (fileId: string | null) => setViewing(batch.files.find((file) => file.id === fileId) ?? null);
  const choose = (id: string, replace: boolean) =>
    setReplaced((current) => (replace ? [...new Set([...current, id])] : current.filter((c) => c !== id)));
  const { steps, otherDocuments } = preview ? buildTimeline(preview) : { steps: [], otherDocuments: [] };
  const countryName =
    (countries.data ?? []).find((c) => c.iso2 === preview?.amm.country_iso2)?.name ??
    preview?.amm.country_iso2;
  const reasons = blocked ? blockingReasons(preview) : [];
  const points = preview && !blocked ? reviewPoints(preview) : [];
  const projection = preview?.projection;

  return (
    <Stack spacing={3}>
      {applied && (
        <Alert
          severity="success"
          action={
            batch.amm_id && (
              <Button component={Link} to={`/amms/${batch.amm_id}`}>
                Ouvrir la fiche AMM
              </Button>
            )
          }
        >
          {batch.auto_applied
            ? 'Import validé automatiquement : lecture sûre, aucune donnée enregistrée n’a été remplacée. '
            : 'Import validé. '}
          Les personnes concernées (siège et réglementaire du pays) ont été notifiées.
        </Alert>
      )}
      {applied && hasSummary(batch.summary) && <DossierImportSummaryCard summary={batch.summary} />}
      {batch.status === 'FAILED' && (
        <Alert severity="error">
          {batch.error || 'L’analyse a échoué. Relancez-la pour réutiliser les documents déjà envoyés.'}
        </Alert>
      )}
      {preview && (
        <>
          <Paper variant="outlined" sx={{ p: 3 }}>
            <Typography variant="h5" component="h2">
              {preview.amm.id ? (
                <MuiLink component={Link} to={`/amms/${preview.amm.id}`}>
                  {preview.amm.product_name || 'Produit non reconnu'}
                </MuiLink>
              ) : (
                preview.amm.product_name || 'Produit non reconnu'
              )}
              {' · '}
              {countryName ? `${countryName}` : 'Pays non reconnu'}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {preview.amm.id
                ? 'AMM déjà enregistrée : le dossier la complète.'
                : 'Nouvelle AMM : elle sera créée à la validation.'}
              {preview.amm.holder ? ` Titulaire : ${preview.amm.holder}.` : ''}
            </Typography>
            {!applied && (
              <Alert severity={blocked ? 'error' : points.length ? 'warning' : 'success'}>
                <AlertTitle sx={{ mb: reasons.length > 1 || points.length ? 1 : 0 }}>
                  {stateSentence(preview)}
                </AlertTitle>
                {(reasons.length > 1 || points.length > 0) && (
                  <Box component="ul" sx={{ m: 0, pl: 2 }}>
                    {(blocked ? reasons.slice(1) : points).map((line, index) => (
                      <li key={index}>{line}</li>
                    ))}
                  </Box>
                )}
              </Alert>
            )}
            <Typography variant="caption" display="block" color="text.secondary" sx={{ mt: 1 }}>
              Fiabilité de la lecture : {preview.confidence} %
            </Typography>
          </Paper>

          <Box>
            <Typography variant="h6" gutterBottom>
              Chronologie de l’AMM
            </Typography>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Stepper orientation="vertical" nonLinear activeStep={-1} aria-label="Chronologie de l’AMM">
                {steps.map((step, index) => (
                  <Step key={step.id} active expanded completed={false} data-testid={`step-${index + 1}`}>
                    <StepLabel icon={index + 1}>
                      <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
                        <Typography fontWeight={600}>{step.title}</Typography>
                        <Typography variant="body2" color="text.secondary">
                          {period(step.start, step.end)}
                        </Typography>
                        <Chip
                          size="small"
                          label={
                            applied && step.action !== 'recorded' ? 'Enregistré' : actionLabels[step.action]
                          }
                          color={applied ? 'default' : actionColors[step.action]}
                          variant={step.action === 'recorded' || applied ? 'outlined' : 'filled'}
                        />
                        {step.inForce && (
                          <Chip size="small" color="success" variant="outlined" label="En vigueur" />
                        )}
                      </Stack>
                    </StepLabel>
                    <StepContent>
                      <TimelineStepContent
                        step={step}
                        applied={applied}
                        replaced={replaced}
                        disabled={busy || blocked || stale}
                        onChoice={choose}
                        view={view}
                      />
                    </StepContent>
                  </Step>
                ))}
              </Stepper>
            </Paper>
          </Box>

          {!applied && projection && (
            <Paper variant="outlined" sx={{ p: 3 }} aria-label="Après validation" component="section">
              <Typography variant="h6" gutterBottom>
                Après validation
              </Typography>
              <Stack spacing={1}>
                <Typography>
                  Échéance en vigueur :{' '}
                  <strong>{formatDate(projection.effective_end_date, 'non déterminée')}</strong>
                </Typography>
                <Stack direction="row" alignItems="center" gap={1}>
                  <Typography>Statut :</Typography>
                  <Chip
                    size="small"
                    label={ammStatusLabels[projection.status] ?? projection.status}
                    color={
                      projection.status === 'VALIDE'
                        ? 'success'
                        : projection.status === 'EXPIRE'
                          ? 'error'
                          : 'default'
                    }
                  />
                </Stack>
                <Typography>
                  {projection.dossier_state === 'COMPLET'
                    ? 'Dossier complet : la décision en vigueur a son scan.'
                    : `Dossier incomplet : il manque le ${projection.missing_scan ?? 'scan de la décision en vigueur'}.`}
                </Typography>
                {replaced.length > 0 && (
                  <Typography variant="caption" color="text.secondary">
                    Calcul fait en gardant les valeurs enregistrées (hors remplacements choisis).
                  </Typography>
                )}
              </Stack>
            </Paper>
          )}

          {otherDocuments.length > 0 && (
            <Accordion variant="outlined" disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography>Autres documents ({otherDocuments.length})</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={1}>
                  {otherDocuments.map((doc) => (
                    <Stack key={doc.file_id} direction="row" alignItems="center" gap={1} flexWrap="wrap">
                      <Button size="small" onClick={() => view(doc.file_id)}>
                        Voir
                      </Button>
                      <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>
                        {fileName(doc.path)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {documentKindLabels[doc.kind] ?? doc.kind} · {periodTitle(doc.period, preview)}
                        {doc.duplicate_id ? ' · déjà présent dans la fiche' : ''}
                      </Typography>
                    </Stack>
                  ))}
                </Stack>
              </AccordionDetails>
            </Accordion>
          )}
        </>
      )}
      {applied && batch.audit.length > 0 && (
        <Accordion variant="outlined" disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>Détail des modifications (traçabilité)</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Information</TableCell>
                    <TableCell>Avant</TableCell>
                    <TableCell>Après</TableCell>
                    <TableCell>Validé par</TableCell>
                    <TableCell>Preuve</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {batch.audit.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell>
                        {fieldLabels[entry.field] ?? entry.field}
                        <Typography variant="caption" display="block">
                          {entry.target === 'amm' ? 'AMM d’origine' : 'Renouvellement'}
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
                          Voir le scan
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
          </AccordionDetails>
        </Accordion>
      )}
      {stale ? (
        <Alert severity="warning">
          Les informations en base ont changé depuis cette analyse. Relancez l’analyse, puis vérifiez de
          nouveau vos choix avant de valider.
        </Alert>
      ) : (
        confirm.isError && <Alert severity="error">{extractErrorMessage(confirm.error)}</Alert>
      )}
      {analyze.isError && <Alert severity="error">{extractErrorMessage(analyze.error)}</Alert>}
      {!applied && (
        <Stack direction="row" flexWrap="wrap" gap={2} alignItems="flex-start">
          {batch.status === 'READY' && (
            <Button
              variant="contained"
              size="large"
              disabled={blocked || busy || stale || !batch.preview_token}
              onClick={() =>
                confirm.mutate({ preview_token: batch.preview_token, accepted_changes: replaced })
              }
            >
              {confirm.isPending ? 'Enregistrement…' : 'Valider'}
            </Button>
          )}
          <TextField
            select
            size="small"
            label="Pays du dossier"
            value={selectedCountry}
            onChange={(event) => setCountry(event.target.value)}
            sx={{ minWidth: 220 }}
            helperText="À préciser si les documents ne nomment pas le pays"
          >
            <MenuItem value="">Détecter automatiquement</MenuItem>
            {allowedCountries.map((c) => (
              <MenuItem key={c.iso2} value={c.iso2}>
                {c.name} ({c.iso2})
              </MenuItem>
            ))}
          </TextField>
          <Button
            variant="outlined"
            disabled={busy}
            onClick={() => analyze.mutate(selectedCountry ? { country: selectedCountry } : {})}
          >
            Relancer l’analyse
          </Button>
        </Stack>
      )}
      <DossierFileViewer batchId={batch.id} file={viewing} onClose={() => setViewing(null)} />
    </Stack>
  );
}

export default function DossierImportDetailPage() {
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
        subtitle={`Import du ${formatDateTime(batch.created_at)}`}
        actions={
          <>
            <Chip label={state.label} color={state.tone} />
            <Button component={Link} to="/dossier-imports">
              Tous les imports de dossiers
            </Button>
          </>
        }
      />
      {running ? (
        <Stack spacing={2}>
          <Alert severity="info">
            Analyse des documents en cours : lecture des scans, reconnaissance de l’AMM et de ses
            renouvellements. Si tout est sûr, l’import sera validé automatiquement. Cette page se met à jour
            automatiquement.
          </Alert>
          <LinearProgress />
        </Stack>
      ) : (
        <PreviewContent key={`${batch.id}-${batch.preview_token}-${batch.status}`} batch={batch} />
      )}
    </Box>
  );
}
