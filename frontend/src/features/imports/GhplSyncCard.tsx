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
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { useGhplSync, useGhplSyncFiles, useMergeGhplCopies, useRunGhplSync } from '@/api/hooks/useGhplSync';
import type { GhplSyncCopy, GhplSyncIssue, GhplSyncRun } from '@/api/types';
import { formatDateTime } from '@/lib/dates';

const STATUS_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default' | 'info'> = {
  DONE: 'success',
  UP_TO_DATE: 'success',
  PARTIAL: 'info',
  RUNNING: 'warning',
  FAILED: 'error',
  NOT_CONFIGURED: 'default',
};

// Les libellés (au singulier et au pluriel) sont dans `excelImports.sync.counters.<clé>` et
// `excelImports.sync.files.<état>`, résolus au rendu pour suivre la langue.
const COUNTERS = [
  'pieces',
  'presentations_changed',
  'downloaded',
  'adopted',
  'moved',
  'skipped',
  'pending',
  'copies_merged',
];

const FILE_STATES: {
  state: string;
  color: 'success' | 'info' | 'warning' | 'error' | 'default';
}[] = [
  { state: 'SYNCED', color: 'success' },
  { state: 'PENDING', color: 'info' },
  { state: 'SKIPPED', color: 'warning' },
  { state: 'REMOVED', color: 'default' },
  { state: 'ERROR', color: 'error' },
];

function count(run: GhplSyncRun | null, key: string): number {
  const value = run?.summary?.[key];
  return typeof value === 'number' ? value : 0;
}

function FilesList({ state }: { state: string }) {
  const { t } = useTranslation();
  const files = useGhplSyncFiles(state);
  if (files.isLoading) return <CircularProgress size={18} />;
  const rows = files.data?.results ?? [];
  if (!rows.length) return <Typography variant="body2">{t('excelImports.sync.noFiles')}</Typography>;
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
          {t('excelImports.sync.shownOf', { shown: rows.length, total: files.data?.count })}
        </caption>
      )}
    </Table>
  );
}

/**
 * Fiches en double (même pays, même présentation sous deux libellés) : les simples copies se
 * fusionnent dans la fiche du pays, sur demande ; les autres sont à vérifier.
 */
function DuplicateRecords({ copies }: { copies: GhplSyncCopy[] }) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const merge = useMergeGhplCopies();
  const [confirming, setConfirming] = useState(false);
  const mergeable = copies.filter((c) => c.mergeable);
  const mergeableLabel = t('excelImports.sync.copies', { count: mergeable.length });
  const send = (pairs: GhplSyncCopy[]) =>
    merge.mutate(
      pairs.map(({ copy, keep }) => ({ copy, keep })),
      {
        onSuccess: (result) => {
          setConfirming(false);
          const merged = t('excelImports.sync.merged', { count: result.merged });
          enqueueSnackbar(
            result.refused.length
              ? t('excelImports.sync.mergedWithRefused', {
                  merged,
                  refusedCount: result.refused.length,
                  reason: result.refused[0].reason,
                })
              : merged,
            { variant: result.refused.length ? 'warning' : 'success' },
          );
        },
        onError: (e) => enqueueSnackbar(extractErrorMessage(e), { variant: 'error' }),
      },
    );
  return (
    <Box sx={{ mt: 2 }} data-testid="ghpl-copies">
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5, flexWrap: 'wrap' }}>
        <Typography variant="subtitle2" sx={{ flex: 1 }}>
          {t('excelImports.sync.duplicatesTitle', { count: copies.length })}
        </Typography>
        {mergeable.length > 0 &&
          (confirming ? (
            <>
              <Button size="small" onClick={() => setConfirming(false)} disabled={merge.isPending}>
                {t('app.cancel')}
              </Button>
              <Button
                size="small"
                color="warning"
                variant="contained"
                onClick={() => send(mergeable)}
                disabled={merge.isPending}
                data-testid="ghpl-copies-confirm"
              >
                {t('excelImports.sync.confirmMerge', { copies: mergeableLabel })}
              </Button>
            </>
          ) : (
            <Button
              size="small"
              variant="outlined"
              onClick={() => setConfirming(true)}
              data-testid="ghpl-copies-merge"
            >
              {t('excelImports.sync.mergeCopies', { copies: mergeableLabel })}
            </Button>
          ))}
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1, fontSize: 12.5 }}>
        {t('excelImports.sync.duplicatesHelp')}
      </Typography>
      <Box sx={{ maxHeight: 360, overflowY: 'auto' }}>
        <Table size="small" stickyHeader>
          <TableBody>
            {copies.map((entry) => (
              <TableRow key={entry.copy}>
                <TableCell sx={{ fontSize: 12, width: 36 }}>{entry.country}</TableCell>
                <TableCell sx={{ fontSize: 12, wordBreak: 'break-word' }}>
                  <MuiLink component={Link} to={`/amms/${entry.copy}`}>
                    {entry.copy_name}
                  </MuiLink>
                  {' → '}
                  <MuiLink component={Link} to={`/amms/${entry.keep}`}>
                    {entry.keep_name}
                  </MuiLink>
                  {!entry.mergeable && (
                    <Typography component="span" sx={{ fontSize: 12, color: 'warning.main' }}>
                      {' '}
                      {t('excelImports.sync.toCheck', { reason: entry.reason })}
                    </Typography>
                  )}
                </TableCell>
                <TableCell sx={{ width: 96, textAlign: 'right' }}>
                  {entry.mergeable && (
                    <Button size="small" onClick={() => send([entry])} disabled={merge.isPending}>
                      {t('excelImports.sync.merge')}
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
    </Box>
  );
}

/**
 * Synchronisation horaire avec le classement AMM GHPL (Nextcloud) : état du dernier passage,
 * ce qu'il a fait, ce qui demande une action, et « Synchroniser maintenant ».
 */
export function GhplSyncCard() {
  const { t } = useTranslation();
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
  const copies = (report?.summary?.copies as GhplSyncCopy[] | undefined) ?? [];
  const launch = () =>
    run.mutate(undefined, {
      onSuccess: () => enqueueSnackbar(t('excelImports.sync.started'), { variant: 'info' }),
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
              {t('excelImports.sync.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('excelImports.sync.description', { folder: data.folder })}
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
            {t('excelImports.sync.runNow')}
          </Button>
        </Stack>

        {!data.configured && (
          <Alert severity="info" sx={{ mb: 1.5 }}>
            {t('excelImports.sync.inactive')}
          </Alert>
        )}
        {last?.status === 'FAILED' && (
          <Alert severity="error" sx={{ mb: 1.5 }}>
            {last.message}
          </Alert>
        )}

        {last && (
          <Typography variant="body2" sx={{ mb: 1 }}>
            {t('excelImports.sync.lastRun', { date: formatDateTime(last.started_at) })}
            {data.last_success?.registry_modified &&
              t('excelImports.sync.registryModified', {
                date: formatDateTime(data.last_success.registry_modified),
              })}
          </Typography>
        )}

        {report && (
          <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1, mb: 1.5 }}>
            {COUNTERS.filter((key) => count(report, key) > 0).map((key) => (
              <Chip
                key={key}
                size="small"
                variant="outlined"
                label={t(`excelImports.sync.counters.${key}`, { count: count(report, key) })}
              />
            ))}
            {report.scans_batch && (
              <Button size="small" component={Link} to={`/admin/imports/${report.scans_batch}`}>
                {t('excelImports.sync.importDetail')}
              </Button>
            )}
          </Stack>
        )}

        <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1 }}>
          {FILE_STATES.filter(({ state }) => (data.files[state] ?? 0) > 0).map(({ state, color }) => (
            <Chip
              key={state}
              size="small"
              color={color}
              variant={open === state ? 'filled' : 'outlined'}
              label={t(`excelImports.sync.files.${state}`, { count: data.files[state] ?? 0 })}
              onClick={() => setOpen(open === state ? null : state)}
              data-testid={`ghpl-files-chip-${state}`}
            />
          ))}
        </Stack>
        <Collapse in={!!open} unmountOnExit>
          <Box sx={{ mt: 1.5 }}>{open && <FilesList state={open} />}</Box>
        </Collapse>

        {copies.length > 0 && <DuplicateRecords copies={copies} />}

        {issues.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              {t('excelImports.sync.toLookAt', {
                total: String(report?.summary?.issues_total ?? issues.length),
              })}
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
