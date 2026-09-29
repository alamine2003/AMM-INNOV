import { useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Collapse,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';
import CreateNewFolderIcon from '@mui/icons-material/CreateNewFolder';
import { useNavigate } from 'react-router';
import { extractErrorMessage } from '@/api/client';
import { useUploadDossier } from '@/api/hooks/useDossierImports';
import { PageHeader } from '@/components/PageHeader';
import { formatBytes } from '@/lib/download';
import { CappedList, plural } from './CappedList';
import { DossierHistory } from './DossierHistory';
import { DossierImportReport } from './DossierImportReport';
import {
  filesFromDrop,
  filesFromPicker,
  setAside,
  splitByProduct,
  validateFolder,
  type FolderFile,
  type ProductGroup,
} from './folderUpload';

const PARALLEL_UPLOADS = 3;

interface Run {
  total: number;
  done: number;
  created: number;
  failed: { group: ProductGroup; reason: string }[];
}

/** Échecs regroupés par motif : « 18 × Serveur injoignable » plutôt que 18 lignes. */
function byReason(failed: Run['failed']) {
  const groups = new Map<string, string[]>();
  for (const { group, reason } of failed) groups.set(reason, [...(groups.get(reason) ?? []), group.name]);
  return [...groups.entries()].map(([reason, names]) => ({ reason, names }));
}

export default function DossierImportsPage() {
  const navigate = useNavigate();
  const picker = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<FolderFile[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [ignored, setIgnored] = useState<string[]>([]);
  const [groups, setGroups] = useState<ProductGroup[]>([]);
  const [progress, setProgress] = useState(0);
  const [reading, setReading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [showFiles, setShowFiles] = useState(false);
  const [showIgnored, setShowIgnored] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const upload = useUploadDossier();
  const running = run !== null && run.done < run.total;
  const busy = reading || upload.isPending || running;

  const select = (selection: FolderFile[]) => {
    upload.reset();
    setRun(null);
    setShowFiles(false);
    setShowIgnored(false);
    const { kept: next, ignored: aside } = setAside(selection);
    setIgnored(aside);
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

  const sendAll = async (targets: ProductGroup[]) => {
    const state: Run = { total: targets.length, done: 0, created: 0, failed: [] };
    setRun({ ...state });
    const sendOne = async (group: ProductGroup) => {
      try {
        await upload.mutateAsync({ files: group.files, onProgress: setProgress });
        state.created += 1;
      } catch (error) {
        state.failed.push({ group, reason: extractErrorMessage(error) });
      }
      state.done += 1;
      setRun({ ...state, failed: [...state.failed] });
    };
    // Le premier produit part seul : les documents communs du dossier pays ne sont envoyés
    // qu'une fois. Les suivants partent trois par trois.
    const [first, ...rest] = targets;
    if (first) await sendOne(first);
    const queue = [...rest];
    await Promise.all(
      Array.from({ length: Math.min(PARALLEL_UPLOADS, queue.length) }, async () => {
        for (let group = queue.shift(); group; group = queue.shift()) await sendOne(group);
      }),
    );
    setFiles([]);
    setGroups([]);
    setIgnored([]);
  };

  const size = files.reduce((total, { file }) => total + file.size, 0);
  const folder = files[0]?.path.split('/')[0];

  return (
    <Box>
      <PageHeader
        title="Import de dossiers AMM"
        subtitle="Déposez un dossier : chaque scan est rangé sur la bonne AMM. Seul ce qui demande votre intervention vous est montré."
      />
      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent sx={{ '&:last-child': { pb: 2 } }}>
          <Stack spacing={1.5}>
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
                display: 'flex',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 2,
                border: '2px dashed',
                borderColor: dragging ? 'primary.main' : 'divider',
                bgcolor: dragging ? 'action.hover' : 'background.default',
                borderRadius: 2,
                px: 2,
                py: 1.5,
              }}
            >
              <CreateNewFolderIcon color="primary" sx={{ fontSize: 32 }} />
              <Box sx={{ flex: '1 1 240px', minWidth: 0 }}>
                <Typography variant="subtitle1" component="p">
                  Glissez un dossier produit, pays ou gamme ici
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  PDF, JPEG, PNG · 25 Mo par fichier · 200 fichiers et 250 Mo par produit
                </Typography>
              </Box>
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
            </Box>
            {reading && <LinearProgress aria-label="Lecture du dossier" />}

            {files.length > 0 && !running && (
              <Box>
                <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
                  <Typography variant="body1" sx={{ fontWeight: 600 }}>
                    {folder}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" data-testid="selection-summary">
                    {plural(files.length, 'fichier', 'fichiers')}
                    {groups.length > 0 && ` · ${plural(groups.length, 'produit', 'produits')}`} ·{' '}
                    {formatBytes(size)}
                  </Typography>
                  <Button size="small" onClick={() => setShowFiles(!showFiles)}>
                    {showFiles ? 'Masquer les fichiers' : 'Voir les fichiers'}
                  </Button>
                  <Box sx={{ flexGrow: 1 }} />
                  <Button
                    variant="contained"
                    disabled={errors.length > 0 || busy}
                    onClick={() =>
                      groups.length
                        ? void sendAll(groups)
                        : upload.mutate(
                            { files, onProgress: setProgress },
                            { onSuccess: (batch) => navigate(`/dossier-imports/${batch.id}`) },
                          )
                    }
                  >
                    {groups.length ? `Analyser les ${groups.length} produits` : 'Analyser le dossier'}
                  </Button>
                </Stack>
                <Collapse in={showFiles} unmountOnExit>
                  <Box
                    component="ul"
                    aria-label="Fichiers sélectionnés"
                    sx={{ maxHeight: 180, overflow: 'auto', my: 1, pl: 3 }}
                  >
                    {files.map(({ path }, index) => (
                      <Typography
                        component="li"
                        key={`${path}-${index}`}
                        variant="caption"
                        display="list-item"
                        sx={{ overflowWrap: 'anywhere' }}
                      >
                        {path.split('/').slice(1).join('/')}
                      </Typography>
                    ))}
                  </Box>
                </Collapse>
              </Box>
            )}

            {errors.length > 0 && (
              <Alert severity="error">
                <Typography variant="subtitle2">
                  {plural(errors.length, 'point à corriger', 'points à corriger')} avant l’envoi
                </Typography>
                <CappedList
                  items={errors}
                  limit={3}
                  itemKey={(_, index) => String(index)}
                  render={(e) => e}
                />
              </Alert>
            )}
            {ignored.length > 0 && !running && (
              <Alert
                severity="info"
                sx={{ py: 0 }}
                action={
                  <Button size="small" color="inherit" onClick={() => setShowIgnored(!showIgnored)}>
                    {showIgnored ? 'Masquer' : 'Voir'}
                  </Button>
                }
              >
                {plural(ignored.length, 'fichier mis de côté', 'fichiers mis de côté')} (format non lu ou plus
                de 25 Mo) ; le reste est envoyé.
                <Collapse in={showIgnored} unmountOnExit>
                  <CappedList items={ignored} limit={10} itemKey={(name) => name} render={(name) => name} />
                </Collapse>
              </Alert>
            )}

            {upload.isPending && !run && (
              <Box>
                <LinearProgress variant="determinate" value={progress} />
                <Typography variant="caption">Envoi des documents : {progress} %</Typography>
              </Box>
            )}
            {upload.isError && !run && <Alert severity="error">{extractErrorMessage(upload.error)}</Alert>}
            {run && (
              <RunStatus
                run={run}
                running={running}
                onRetry={() => void sendAll(run.failed.map((f) => f.group))}
              />
            )}
          </Stack>
        </CardContent>
      </Card>

      <DossierImportReport />
      <DossierHistory />
    </Box>
  );
}

/** Une barre pendant l'envoi ; à la fin, une ligne de bilan et les échecs regroupés par motif. */
function RunStatus({ run, running, onRetry }: { run: Run; running: boolean; onRetry: () => void }) {
  if (running) {
    return (
      <Box>
        <LinearProgress
          variant="determinate"
          value={Math.round((run.done / run.total) * 100)}
          aria-label="Envoi des produits"
        />
        <Typography variant="caption" color="text.secondary">
          Envoi des produits : {run.done} / {run.total}
          {run.failed.length > 0 && ` · ${run.failed.length} en échec`}
        </Typography>
      </Box>
    );
  }
  return (
    <Stack spacing={1}>
      {run.created > 0 && (
        <Alert severity="success" sx={{ py: 0 }}>
          {plural(run.created, 'produit envoyé', 'produits envoyés')} : le classement se poursuit tout seul.
        </Alert>
      )}
      {run.failed.length > 0 && (
        <Alert
          severity="warning"
          action={
            <Button size="small" color="inherit" onClick={onRetry}>
              Réessayer
            </Button>
          }
        >
          <Typography variant="subtitle2">
            {plural(run.failed.length, 'produit non envoyé', 'produits non envoyés')}
          </Typography>
          {byReason(run.failed).map(({ reason, names }) => (
            <Typography key={reason} variant="body2" title={names.join('\n')}>
              {names.length} × {reason}
              {names.length <= 3 && ` (${names.join(', ')})`}
            </Typography>
          ))}
        </Alert>
      )}
    </Stack>
  );
}
