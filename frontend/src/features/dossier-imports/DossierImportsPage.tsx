import { useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  Link as MuiLink,
  Pagination,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import CreateNewFolderIcon from '@mui/icons-material/CreateNewFolder';
import { Link, useNavigate } from 'react-router';
import { extractErrorMessage } from '@/api/client';
import { useDossierImports, useUploadDossier } from '@/api/hooks/useDossierImports';
import { hasSummary } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { formatDateTime } from '@/lib/dates';
import { formatBytes } from '@/lib/download';
import {
  filesFromDrop,
  filesFromPicker,
  splitByProduct,
  validateFolder,
  type FolderFile,
  type ProductGroup,
} from './folderUpload';

export const dossierStatusLabels = {
  PENDING: 'En attente',
  RUNNING: 'Analyse en cours',
  READY: 'À vérifier',
  APPLIED: 'Import validé',
  FAILED: 'Échec de l’analyse',
};

export default function DossierImportsPage() {
  const navigate = useNavigate();
  const picker = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<FolderFile[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);
  const [reading, setReading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [page, setPage] = useState(1);
  const batches = useDossierImports(page);
  const upload = useUploadDossier();
  const [groups, setGroups] = useState<ProductGroup[]>([]);
  const [batchRun, setBatchRun] = useState<{ done: number; created: number; failed: string[] } | null>(null);
  const running = batchRun !== null && batchRun.done < groups.length;
  const busy = reading || upload.isPending || running;
  const select = (next: FolderFile[]) => {
    upload.reset();
    setBatchRun(null);
    const split = splitByProduct(next);
    setGroups(split);
    setFiles(next);
    // Dossier pays : chaque produit est un import distinct, les limites s'appliquent par produit.
    setErrors(
      split.length
        ? split.flatMap((group) => validateFolder(group.files).map((error) => `${group.name} : ${error}`))
        : validateFolder(next),
    );
    setProgress(0);
  };
  const analyzeAll = async () => {
    const run = { done: 0, created: 0, failed: [] as string[] };
    setBatchRun({ ...run });
    for (const group of groups) {
      try {
        await upload.mutateAsync({ files: group.files, onProgress: setProgress });
        run.created += 1;
      } catch (error) {
        run.failed.push(`${group.name} : ${extractErrorMessage(error)}`);
      }
      run.done += 1;
      setBatchRun({ ...run });
    }
    setFiles([]);
    setGroups([]);
  };

  return (
    <Box>
      <PageHeader
        title="Import intelligent de dossiers AMM"
        subtitle="Sélectionnez un dossier complet. Vérifiez les documents, les rattachements et les corrections proposées avant de valider."
      />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack spacing={2}>
            <Box
              onDragOver={(event) => {
                event.preventDefault();
                if (!busy) setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={async (event) => {
                event.preventDefault();
                setDragging(false);
                if (busy) return;
                setReading(true);
                try {
                  select(await filesFromDrop(event.dataTransfer.items));
                } catch (error) {
                  setFiles([]);
                  setErrors([extractErrorMessage(error)]);
                } finally {
                  setReading(false);
                }
              }}
              sx={{
                border: '2px dashed',
                borderColor: dragging ? 'primary.main' : 'divider',
                bgcolor: dragging ? 'action.hover' : 'background.default',
                borderRadius: 2,
                p: 4,
                textAlign: 'center',
              }}
            >
              <CreateNewFolderIcon color="primary" sx={{ fontSize: 36, mb: 1 }} />
              <Typography variant="h6">Déposez votre dossier AMM ici</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ my: 1 }}>
                Sous-dossiers conservés · PDF, JPEG et PNG · 200 fichiers maximum
              </Typography>
              <Button variant="outlined" disabled={busy} onClick={() => picker.current?.click()}>
                Choisir un dossier
              </Button>
              <input
                ref={picker}
                type="file"
                multiple
                {...{ webkitdirectory: '', directory: '' }}
                aria-label="Dossier AMM"
                style={{ display: 'none' }}
                onChange={(event) => {
                  if (event.target.files) select(filesFromPicker(event.target.files));
                  event.target.value = '';
                }}
              />
              <Typography variant="caption" display="block" color="text.secondary" sx={{ mt: 1 }}>
                25 Mo par fichier, 250 Mo par dossier. Utilisez le bouton si le glisser-déposer n’est pas pris
                en charge.
              </Typography>
            </Box>
            {reading && <LinearProgress aria-label="Lecture du dossier" />}
            {files.length > 0 && (
              <Box>
                <Typography variant="subtitle1">
                  {files[0].path.split('/')[0]} — {files.length} fichiers ·{' '}
                  {formatBytes(files.reduce((total, { file }) => total + file.size, 0))}
                </Typography>
                <Box
                  component="ul"
                  aria-label="Fichiers sélectionnés"
                  sx={{ maxHeight: 220, overflow: 'auto', my: 1, pl: 3 }}
                >
                  {files.map(({ path }, index) => (
                    <Typography
                      component="li"
                      key={`${path}-${index}`}
                      variant="body2"
                      sx={{ overflowWrap: 'anywhere' }}
                    >
                      {path}
                    </Typography>
                  ))}
                </Box>
              </Box>
            )}
            {errors.length > 0 && (
              <Alert severity="error">
                <Box component="ul" sx={{ m: 0, pl: 2 }}>
                  {errors.slice(0, 12).map((error, index) => (
                    <li key={index}>{error}</li>
                  ))}
                  {errors.length > 12 && <li>{errors.length - 12} autres fichiers à vérifier.</li>}
                </Box>
              </Alert>
            )}
            {groups.length > 0 && (
              <Alert severity="info">
                Ce dossier regroupe {groups.length} produits : chacun sera analysé comme un import séparé.
                Vous vérifierez et validerez ensuite chaque produit dans l’historique ci-dessous.
              </Alert>
            )}
            {batchRun && (
              <Alert severity={batchRun.failed.length ? 'warning' : 'success'}>
                {running
                  ? `Envoi des produits : ${batchRun.done + 1} / ${groups.length}…`
                  : `${batchRun.created} import(s) créé(s). Ouvrez chacun dans l’historique pour vérifier et valider.`}
                {batchRun.failed.length > 0 && (
                  <Box component="ul" sx={{ m: 0, pl: 2 }}>
                    {batchRun.failed.map((failure) => (
                      <li key={failure}>{failure}</li>
                    ))}
                  </Box>
                )}
              </Alert>
            )}
            {upload.isError && !groups.length && !batchRun && (
              <Alert severity="error">{extractErrorMessage(upload.error)}</Alert>
            )}
            {upload.isPending && (
              <Box>
                <LinearProgress variant="determinate" value={progress} />
                <Typography variant="caption">Envoi des documents : {progress} %</Typography>
              </Box>
            )}
            <Box>
              <Button
                variant="contained"
                disabled={!files.length || errors.length > 0 || busy}
                onClick={() =>
                  groups.length
                    ? void analyzeAll()
                    : upload.mutate(
                        { files, onProgress: setProgress },
                        { onSuccess: (batch) => navigate(`/dossier-imports/${batch.id}`) },
                      )
                }
              >
                {groups.length ? `Analyser les ${groups.length} produits` : 'Analyser le dossier'}
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>
      <Typography variant="h6" gutterBottom>
        Historique des dossiers importés
      </Typography>
      {batches.isPending ? (
        <LoadingBlock />
      ) : batches.isError ? (
        <ErrorBlock error={batches.error} onRetry={() => batches.refetch()} />
      ) : (
        <Paper variant="outlined">
          {!batches.data.results.length ? (
            <EmptyBlock text="Aucun dossier importé." />
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Dossier</TableCell>
                    <TableCell>Date</TableCell>
                    <TableCell>AMM touchée et changements</TableCell>
                    <TableCell>État</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {batches.data.results.map((batch) => (
                    <TableRow key={batch.id}>
                      <TableCell>
                        <MuiLink component={Link} to={`/dossier-imports/${batch.id}`}>
                          {batch.root_name}
                        </MuiLink>
                      </TableCell>
                      <TableCell>{formatDateTime(batch.created_at)}</TableCell>
                      <TableCell>
                        {hasSummary(batch.summary) ? (
                          <>
                            <MuiLink component={Link} to={`/amms/${batch.summary.amm_id}`}>
                              {batch.summary.product} ({batch.summary.country_iso2})
                            </MuiLink>
                            {batch.summary.lines
                              .filter((line) => /^(Statut|Dossier|Échéance|AMM créée)/.test(line))
                              .map((line) => (
                                <Typography
                                  key={line}
                                  variant="caption"
                                  display="block"
                                  color="text.secondary"
                                >
                                  {line}
                                </Typography>
                              ))}
                          </>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          label={dossierStatusLabels[batch.status]}
                          color={
                            batch.status === 'APPLIED'
                              ? 'success'
                              : batch.status === 'FAILED'
                                ? 'error'
                                : 'default'
                          }
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
          {batches.data.count > 20 && (
            <Pagination
              page={page}
              count={Math.ceil(batches.data.count / 20)}
              onChange={(_, value) => setPage(value)}
              sx={{ p: 2 }}
            />
          )}
        </Paper>
      )}
    </Box>
  );
}
