import { useState } from 'react';
import axios from 'axios';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  LinearProgress,
  Link as MuiLink,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { Link, useParams, useSearchParams } from 'react-router';
import { extractErrorMessage } from '@/api/client';
import { useAnalyzeDossier, useConfirmDossier, useDossierImport } from '@/api/hooks/useDossierImports';
import { useCountries } from '@/api/hooks/useCatalog';
import { useAuthStore } from '@/features/auth/authStore';
import { hasSummary, type DossierImportBatch, type DossierImportFile } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { formatDate, formatDateTime } from '@/lib/dates';
import { DossierFileViewer } from './DossierFileViewer';
import { dossierStatusLabels } from './DossierImportsPage';
import { DossierImportSummaryCard } from './DossierImportSummaryCard';

export const showDossierValue = (value: unknown) =>
  value === null || value === undefined || value === ''
    ? '—'
    : typeof value === 'object'
      ? JSON.stringify(value)
      : String(value);
const fields: Record<string, string> = {
  original_number: 'Numéro AMM d’origine',
  original_start_date: 'Délivrance de l’AMM d’origine',
  original_end_date: 'Échéance de l’AMM d’origine',
  holder: 'Titulaire / laboratoire',
  number: 'Numéro de renouvellement',
  start_date: 'Date de début',
  end_date: 'Date d’échéance',
  decision_date: 'Date de décision',
  workflow_status: 'État du renouvellement',
  dossier_state: 'État du dossier',
  product: 'Produit',
  country: 'Pays',
  document: 'Document',
  created: 'Création',
};
const levelLabels = { HIGH: 'élevée', MEDIUM: 'moyenne', LOW: 'faible' };

function PreviewContent({ batch }: { batch: DossierImportBatch }) {
  const preview = batch.preview;
  const [search] = useSearchParams();
  const [viewing, setViewing] = useState<DossierImportFile | null>(
    () => batch.files.find((file) => file.id === search.get('file')) ?? null,
  );
  const [accepted, setAccepted] = useState<string[]>([]);
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
  const blocked = !preview || !preview.can_apply || preview.level === 'LOW' || preview.blockers.length > 0;
  const proof = (fileId: string | null) => {
    const file = batch.files.find((entry) => entry.id === fileId);
    return file ? (
      <Button
        size="small"
        sx={{ textTransform: 'none', textAlign: 'left', overflowWrap: 'anywhere' }}
        onClick={() => setViewing(file)}
      >
        Examiner : {file.relative_path.split('/').at(-1)}
      </Button>
    ) : (
      <Typography variant="caption" color="text.secondary">
        Preuve indisponible
      </Typography>
    );
  };
  const target = (value: string) =>
    value === 'amm' ? 'AMM d’origine' : `Renouvellement : ${value.replace(/^renewal[-:]/, '')}`;
  const docs = [...(preview?.documents ?? [])].sort((a, b) => a.path.localeCompare(b.path));

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
          Import validé. Les personnes concernées (siège et réglementaire du pays) ont été notifiées.
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
            <Stack direction="row" alignItems="center" flexWrap="wrap" gap={1} sx={{ mb: 1 }}>
              <Typography variant="h6">
                {preview.amm.id ? 'AMM reconnue' : 'AMM proposée'} :{' '}
                {preview.amm.product_name || 'Produit non identifié'}
              </Typography>
              <Chip
                label={`Confiance ${levelLabels[preview.level]} : ${preview.confidence} %`}
                color={
                  preview.level === 'HIGH' ? 'success' : preview.level === 'MEDIUM' ? 'warning' : 'error'
                }
              />
            </Stack>
            <Typography>
              Pays : {preview.amm.country_iso2 || 'Non identifié'} · Titulaire / laboratoire :{' '}
              {preview.amm.holder || 'Non identifié'}
            </Typography>
            {preview.amm.id ? (
              <MuiLink component={Link} to={`/amms/${preview.amm.id}`}>
                Consulter les informations actuelles de l’AMM
              </MuiLink>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Une AMM sera créée si les informations permettent de valider l’import.
              </Typography>
            )}
            {Object.keys(preview.original).length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle2">Informations extraites de l’AMM d’origine</Typography>
                {Object.entries(preview.original).map(([field, value]) => (
                  <Typography key={field} variant="body2">
                    {fields[field] || field} : {showDossierValue(value)}
                  </Typography>
                ))}
              </Box>
            )}
            <Box component="ul" sx={{ mb: 0, pl: 2.5 }}>
              <li>
                {docs.filter((doc) => !doc.duplicate_id).length} documents à rattacher ;{' '}
                {docs.filter((doc) => doc.duplicate_id).length} documents déjà présents.
              </li>
              <li>
                {preview.renewals.filter((renewal) => renewal.existing_id).length} renouvellements reconnus ;{' '}
                {preview.renewals.filter((renewal) => !renewal.existing_id).length} renouvellements à créer.
              </li>
              <li>
                {preview.changes.filter((change) => !change.requires_confirmation).length} informations à
                compléter ; {preview.changes.filter((change) => change.requires_confirmation).length}{' '}
                corrections à examiner.
              </li>
            </Box>
          </Paper>
          {preview.blockers.map((message, index) => (
            <Alert severity="error" key={`blocker-${index}`}>
              {message}
            </Alert>
          ))}
          {preview.level === 'LOW' && (
            <Alert severity="warning">
              Confiance insuffisante : aucune donnée métier ne peut être modifiée. Examinez les documents et
              les correspondances avant une nouvelle analyse.
            </Alert>
          )}
          {preview.warnings.map((message, index) => (
            <Alert severity="warning" key={`warning-${index}`}>
              {message}
            </Alert>
          ))}
          {preview.candidates.length > 0 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Correspondances examinées
              </Typography>
              <Stack spacing={1}>
                {preview.candidates.map((candidate) => (
                  <Paper variant="outlined" key={candidate.id} sx={{ p: 2 }}>
                    <Typography>
                      <MuiLink component={Link} to={`/amms/${candidate.id}`}>
                        {candidate.product_name} · {candidate.country_iso2}
                      </MuiLink>{' '}
                      — {candidate.confidence} %
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {candidate.reasons.join(' · ')}
                    </Typography>
                  </Paper>
                ))}
              </Stack>
            </Box>
          )}
          {preview.renewals.length > 0 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Renouvellements
              </Typography>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Action</TableCell>
                      <TableCell>Période / numéro</TableCell>
                      <TableCell>Décision</TableCell>
                      <TableCell>Validité</TableCell>
                      <TableCell>Preuve</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {preview.renewals.map((renewal) => (
                      <TableRow key={renewal.key}>
                        <TableCell>
                          <Chip
                            size="small"
                            variant="outlined"
                            label={
                              renewal.existing_id ? 'Renouvellement existant' : 'Créer un renouvellement'
                            }
                            color={renewal.existing_id ? 'default' : 'primary'}
                          />
                        </TableCell>
                        <TableCell>
                          {renewal.key}
                          <br />
                          {renewal.number || 'Numéro non trouvé'}
                        </TableCell>
                        <TableCell>{formatDate(renewal.decision_date)}</TableCell>
                        <TableCell>
                          {formatDate(renewal.start_date)} → {formatDate(renewal.end_date)}
                        </TableCell>
                        <TableCell>
                          {proof(renewal.proof_file_id)}
                          <Typography variant="caption" display="block">
                            Confiance : {renewal.confidence} %
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}
          {!applied && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Informations à compléter et corrections proposées
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Les champs manquants seront complétés à la validation. Pour remplacer une valeur existante,
                cochez explicitement la correction ; une correction non cochée sera ignorée.
              </Typography>
              {preview.changes.length === 0 ? (
                <Typography>Aucune modification des champs existants.</Typography>
              ) : (
                <TableContainer component={Paper} variant="outlined">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Information</TableCell>
                        <TableCell>Valeur en base</TableCell>
                        <TableCell>Valeur du document</TableCell>
                        <TableCell>Preuve</TableCell>
                        <TableCell>Décision</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {preview.changes.map((change) => (
                        <TableRow key={change.id} data-testid={`change-${change.id}`}>
                          <TableCell>
                            {fields[change.field] || change.field}
                            <Typography variant="caption" display="block">
                              {target(change.target)}
                            </Typography>
                          </TableCell>
                          <TableCell sx={{ overflowWrap: 'anywhere' }}>
                            {showDossierValue(change.old)}
                          </TableCell>
                          <TableCell sx={{ fontWeight: 600, overflowWrap: 'anywhere' }}>
                            {showDossierValue(change.new)}
                          </TableCell>
                          <TableCell>
                            {proof(change.proof_file_id)}
                            <Typography variant="caption" display="block">
                              {change.confidence} %
                            </Typography>
                          </TableCell>
                          <TableCell>
                            {change.requires_confirmation ? (
                              <FormControlLabel
                                control={
                                  <Checkbox
                                    checked={accepted.includes(change.id)}
                                    disabled={busy || blocked || stale}
                                    onChange={(event) =>
                                      setAccepted((current) =>
                                        event.target.checked
                                          ? [...current, change.id]
                                          : current.filter((id) => id !== change.id),
                                      )
                                    }
                                    inputProps={{
                                      'aria-label': `Valider la correction ${fields[change.field] || change.field} (${target(change.target)})`,
                                    }}
                                  />
                                }
                                label={
                                  accepted.includes(change.id)
                                    ? 'Correction sélectionnée'
                                    : 'Ignorer cette correction'
                                }
                              />
                            ) : (
                              <Chip size="small" label="Compléter à la validation" variant="outlined" />
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </Box>
          )}
        </>
      )}
      <Box>
        <Typography variant="h6" gutterBottom>
          Documents du dossier
        </Typography>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Box component="ul" sx={{ m: 0, p: 0, listStyle: 'none' }}>
            {[...batch.files]
              .sort((a, b) => a.relative_path.localeCompare(b.relative_path))
              .map((file) => {
                const doc = docs.find((entry) => entry.file_id === file.id);
                return (
                  <Box
                    component="li"
                    key={file.id}
                    sx={{
                      py: 1,
                      pl: Math.min(file.relative_path.split('/').length - 2, 5) * 2,
                      borderBottom: '1px solid',
                      borderColor: 'divider',
                    }}
                  >
                    <Button
                      sx={{ textTransform: 'none', overflowWrap: 'anywhere', textAlign: 'left' }}
                      onClick={() => setViewing(file)}
                    >
                      {file.relative_path}
                    </Button>
                    {doc && (
                      <Stack direction="row" flexWrap="wrap" gap={1} sx={{ px: 1 }}>
                        <Chip size="small" label={doc.kind} variant="outlined" />
                        <Typography variant="caption">
                          {doc.period === 'original' ? 'AMM d’origine' : `Renouvellement : ${doc.period}`} ·{' '}
                          {formatDate(doc.document_date)}
                        </Typography>
                        {doc.duplicate_id && (
                          <Chip
                            size="small"
                            label="Document déjà présent — conservé"
                            color="info"
                            variant="outlined"
                          />
                        )}
                      </Stack>
                    )}
                  </Box>
                );
              })}
          </Box>
        </Paper>
      </Box>
      {applied && (
        <Box>
          <Typography variant="h6" gutterBottom>
            Historique et preuves de l’import
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Origine : dossier réglementaire importé. Chaque modification conserve sa valeur précédente, sa
            preuve et son validateur.
          </Typography>
          {batch.audit.length ? (
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Champ / cible</TableCell>
                    <TableCell>Ancienne valeur</TableCell>
                    <TableCell>Nouvelle valeur</TableCell>
                    <TableCell>Validation</TableCell>
                    <TableCell>Preuve / motif</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {batch.audit.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell>
                        {fields[entry.field] || entry.field}
                        <Typography variant="caption" display="block">
                          {target(entry.target)}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ overflowWrap: 'anywhere' }}>
                        {showDossierValue(entry.old_value)}
                      </TableCell>
                      <TableCell sx={{ overflowWrap: 'anywhere' }}>
                        {showDossierValue(entry.new_value)}
                      </TableCell>
                      <TableCell>
                        {entry.user_email}
                        <Typography variant="caption" display="block">
                          {formatDateTime(entry.created_at)} · {entry.confidence} %
                        </Typography>
                      </TableCell>
                      <TableCell>
                        {proof(entry.proof_file_id)}
                        <Typography variant="caption" display="block">
                          {entry.reason}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Typography>Aucun champ n’a été modifié lors de cet import.</Typography>
          )}
        </Box>
      )}
      {stale ? (
        <Alert severity="warning">
          Les informations en base ont changé depuis cette prévisualisation. Relancez l’analyse, puis vérifiez
          de nouveau les corrections avant de valider.
        </Alert>
      ) : (
        confirm.isError && <Alert severity="error">{extractErrorMessage(confirm.error)}</Alert>
      )}
      {analyze.isError && <Alert severity="error">{extractErrorMessage(analyze.error)}</Alert>}
      {!applied && (
        <Stack direction="row" flexWrap="wrap" gap={2}>
          {batch.status === 'READY' && (
            <Button
              variant="contained"
              disabled={blocked || busy || stale || !batch.preview_token}
              onClick={() =>
                confirm.mutate({ preview_token: batch.preview_token, accepted_changes: accepted })
              }
            >
              {confirm.isPending
                ? 'Enregistrement…'
                : `Valider l’import${accepted.length ? ` et ${accepted.length} correction${accepted.length > 1 ? 's' : ''}` : ''}`}
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
  return (
    <Box>
      <PageHeader
        title={batch.root_name}
        subtitle={`Import du ${formatDateTime(batch.created_at)}`}
        actions={
          <>
            <Chip label={dossierStatusLabels[batch.status]} />
            <Button component={Link} to="/dossier-imports">
              Tous les imports de dossiers
            </Button>
          </>
        }
      />
      {running ? (
        <Stack spacing={2}>
          <Alert severity="info">
            Analyse des documents en cours : extraction du texte, reconnaissance de l’AMM et vérification des
            éléments existants. Cette page se met à jour automatiquement.
          </Alert>
          <LinearProgress />
        </Stack>
      ) : (
        <PreviewContent key={`${batch.id}-${batch.preview_token}-${batch.status}`} batch={batch} />
      )}
    </Box>
  );
}
