import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Collapse,
  Link as MuiLink,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Typography,
} from '@mui/material';
import SyncIcon from '@mui/icons-material/Sync';
import CloudDoneIcon from '@mui/icons-material/CloudDone';
import { Link } from 'react-router';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { useGhplSync, useGhplSyncFiles, useRunGhplSync } from '@/api/hooks/useGhplSync';
import type { GhplSyncIssue, GhplSyncRun } from '@/api/types';
import { formatDateTime } from '@/lib/dates';

const STATUS_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default' | 'info'> = {
  DONE: 'success',
  UP_TO_DATE: 'success',
  PARTIAL: 'info',
  RUNNING: 'warning',
  FAILED: 'error',
  NOT_CONFIGURED: 'default',
};

const COUNTERS: { key: string; label: [string, string] }[] = [
  { key: 'pieces', label: ['pièce suivie', 'pièces suivies'] },
  { key: 'presentations_changed', label: ['présentation mise à jour', 'présentations mises à jour'] },
  { key: 'downloaded', label: ['scan ajouté', 'scans ajoutés'] },
  { key: 'adopted', label: ['déjà dans AMM GH', 'déjà dans AMM GH'] },
  { key: 'moved', label: ['reclassé', 'reclassés'] },
  { key: 'skipped', label: ['laissé de côté', 'laissés de côté'] },
  { key: 'pending', label: ['en attente', 'en attente'] },
];

const plural = (n: number, [one, many]: [string, string]) => `${n} ${n > 1 ? many : one}`;

const FILE_STATES: {
  state: string;
  label: [string, string];
  color: 'success' | 'info' | 'warning' | 'error' | 'default';
}[] = [
  { state: 'SYNCED', label: ['rangé', 'rangés'], color: 'success' },
  { state: 'PENDING', label: ['à télécharger', 'à télécharger'], color: 'info' },
  { state: 'SKIPPED', label: ['laissé de côté', 'laissés de côté'], color: 'warning' },
  { state: 'REMOVED', label: ['retiré du classement', 'retirés du classement'], color: 'default' },
  { state: 'ERROR', label: ['en erreur', 'en erreur'], color: 'error' },
];

function count(run: GhplSyncRun | null, key: string): number {
  const value = run?.summary?.[key];
  return typeof value === 'number' ? value : 0;
}

function FilesList({ state }: { state: string }) {
  const files = useGhplSyncFiles(state);
  if (files.isLoading) return <CircularProgress size={18} />;
  const rows = files.data?.results ?? [];
  if (!rows.length) return <Typography variant="body2">Aucun fichier.</Typography>;
  return (
    <Table size="small" data-testid={`ghpl-files-${state}`}>
      <TableBody>
        {rows.map((file) => (
          <TableRow key={file.id}>
            <TableCell sx={{ wordBreak: 'break-word', fontSize: 12 }}>
              {file.amm ? (
                <MuiLink component={Link} to={`/amms/${file.amm}?tab=documents`}>
                  {file.path.split('/').slice(-2).join(' / ')}
                </MuiLink>
              ) : (
                file.path.split('/').slice(-2).join(' / ')
              )}
            </TableCell>
            <TableCell sx={{ fontSize: 12, color: 'text.secondary' }}>{file.message}</TableCell>
          </TableRow>
        ))}
      </TableBody>
      {(files.data?.count ?? 0) > rows.length && (
        <caption style={{ captionSide: 'bottom', fontSize: 12 }}>
          {rows.length} affichés sur {files.data?.count}
        </caption>
      )}
    </Table>
  );
}

/**
 * Synchronisation horaire avec le classement AMM GHPL (Nextcloud) : état du dernier passage,
 * ce qu'il a fait, ce qui demande une action, et « Synchroniser maintenant ».
 */
export function GhplSyncCard() {
  const { enqueueSnackbar } = useSnackbar();
  const sync = useGhplSync();
  const run = useRunGhplSync();
  const [open, setOpen] = useState<string | null>(null);
  const data = sync.data;
  if (!data) return null;
  const last = data.last_run;
  // Bilan : le dernier passage qui a lu le registre (un passage « déjà à jour » n'a rien à dire).
  const report = data.recent.find((r) => r.status === 'DONE' || r.status === 'PARTIAL') ?? null;
  const issues = ((report?.summary?.issues as GhplSyncIssue[] | undefined) ?? []).slice(0, 12);
  const launch = () =>
    run.mutate(undefined, {
      onSuccess: () => enqueueSnackbar('Synchronisation lancée', { variant: 'info' }),
      onError: (e) => enqueueSnackbar(extractErrorMessage(e), { variant: 'error' }),
    });

  return (
    <Card variant="outlined" sx={{ mb: 3 }} data-testid="ghpl-sync-card">
      <CardContent>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1.5}
          sx={{ alignItems: { sm: 'center' }, mb: 1.5 }}
        >
          <CloudDoneIcon color="primary" />
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" sx={{ lineHeight: 1.2 }}>
              Synchronisation avec AMM GHPL
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Chaque heure, AMM GH relit le registre du classement « {data.folder} » sur Nextcloud : nouvelles
              AMM, renouvellements, scans ajoutés ou reclassés.
            </Typography>
          </Box>
          {last && (
            <Chip
              color={STATUS_COLOR[last.status] ?? 'default'}
              label={last.status_label}
              icon={data.running ? <CircularProgress size={14} color="inherit" /> : undefined}
              data-testid="ghpl-sync-status"
            />
          )}
          <Button
            variant="contained"
            startIcon={<SyncIcon />}
            onClick={launch}
            disabled={data.running || run.isPending || !data.configured}
            data-testid="ghpl-sync-run"
          >
            Synchroniser maintenant
          </Button>
        </Stack>

        {!data.configured && (
          <Alert severity="info" sx={{ mb: 1.5 }}>
            Synchronisation inactive : Nextcloud n'est pas encore relié. Dans Nextcloud, créez un mot de passe
            d'application (Paramètres personnels &gt; Sécurité), puis collez-le dans Render (variable
            NEXTCLOUD_APP_PASSWORD du service amm-innov-api).
          </Alert>
        )}
        {last?.status === 'FAILED' && (
          <Alert severity="error" sx={{ mb: 1.5 }}>
            {last.message}
          </Alert>
        )}

        {last && (
          <Typography variant="body2" sx={{ mb: 1 }}>
            Dernier passage : {formatDateTime(last.started_at)}
            {data.last_success?.registry_modified &&
              ` · registre du classement modifié le ${formatDateTime(data.last_success.registry_modified)}`}
          </Typography>
        )}

        {report && (
          <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1, mb: 1.5 }}>
            {COUNTERS.filter(({ key }) => count(report, key) > 0).map(({ key, label }) => (
              <Chip key={key} size="small" variant="outlined" label={plural(count(report, key), label)} />
            ))}
            {report.scans_batch && (
              <Button size="small" component={Link} to={`/admin/imports/${report.scans_batch}`}>
                Détail de l'import
              </Button>
            )}
          </Stack>
        )}

        <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1 }}>
          {FILE_STATES.filter(({ state }) => (data.files[state] ?? 0) > 0).map(({ state, label, color }) => (
            <Chip
              key={state}
              size="small"
              color={color}
              variant={open === state ? 'filled' : 'outlined'}
              label={plural(data.files[state] ?? 0, label)}
              onClick={() => setOpen(open === state ? null : state)}
              data-testid={`ghpl-files-chip-${state}`}
            />
          ))}
        </Stack>
        <Collapse in={!!open} unmountOnExit>
          <Box sx={{ mt: 1.5 }}>{open && <FilesList state={open} />}</Box>
        </Collapse>

        {issues.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              À regarder ({String(report?.summary?.issues_total ?? issues.length)})
            </Typography>
            {issues.map((issue) => (
              <Typography key={issue.path} variant="body2" sx={{ fontSize: 12.5 }}>
                <b>{issue.path.split('/').slice(-1)[0]}</b> — {issue.message}
              </Typography>
            ))}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
