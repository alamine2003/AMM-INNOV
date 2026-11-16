import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  LinearProgress,
  ListItemText,
  Menu,
  MenuItem,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import {
  fetchBinderExportFile,
  fetchBinderPdf,
  useBinderExports,
  useStartBinderExport,
} from '@/api/hooks/useBinders';
import type { BinderExport } from '@/api/types';
import { formatDateTime } from '@/lib/dates';
import { formatBytes, saveBlob } from '@/lib/download';

function ExportStatus({ item }: { item: BinderExport }) {
  const { t } = useTranslation();
  if (item.status === 'PENDING' || item.status === 'RUNNING') {
    const progress = item.progress_total ? (item.progress_done / item.progress_total) * 100 : 0;
    return (
      <Box>
        <Typography variant="body2" sx={{ mb: 1 }}>
          {item.status === 'PENDING'
            ? t('binders.download.waiting')
            : t('binders.download.preparing', {
                done: item.progress_done,
                total: item.progress_total || '?',
              })}
        </Typography>
        <LinearProgress
          variant={item.progress_total ? 'determinate' : 'indeterminate'}
          value={progress}
          aria-label={t('binders.download.progressLabel')}
        />
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          {t('binders.download.canClose')}
        </Typography>
      </Box>
    );
  }
  if (item.status === 'FAILED') {
    return <Alert severity="error">{item.error || t('binders.download.failed')}</Alert>;
  }
  return (
    <Alert severity="success" icon={false}>
      <Typography variant="subtitle2">
        {t('binders.download.ready', {
          date: formatDateTime(item.finished_at),
          pages: item.page_count,
          size: formatBytes(item.size_bytes),
        })}
      </Typography>
      <Typography variant="body2">
        {t('binders.download.summary', { count: item.decisions, withoutScan: item.without_scan })}
        {item.unavailable > 0 ? ` · ${t('binders.download.unavailable', { n: item.unavailable })}` : ''}
      </Typography>
    </Alert>
  );
}

/** Classeur complet avec les décisions officielles : préparé en arrière-plan puis téléchargé. */
function OfficialExportDialog({
  binderKey,
  label,
  open,
  onClose,
}: {
  binderKey: string;
  label: string;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const exports = useBinderExports(binderKey, open);
  const start = useStartBinderExport(binderKey);
  const [downloading, setDownloading] = useState(false);
  const latest = exports.data?.[0];
  const ready = exports.data?.find((item) => item.status === 'READY' && item.has_file);
  const busy = latest?.status === 'PENDING' || latest?.status === 'RUNNING';

  const download = async (item: BinderExport) => {
    setDownloading(true);
    try {
      const day = (item.finished_at ?? '').slice(0, 10);
      saveBlob(await fetchBinderExportFile(binderKey, item.id), `Classeur_${binderKey}_decisions_${day}.pdf`);
    } catch (e) {
      enqueueSnackbar(extractErrorMessage(e), { variant: 'error' });
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('binders.download.officialTitle', { label })}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('binders.download.officialIntro')}
        </Typography>
        {exports.isPending ? (
          <LinearProgress />
        ) : exports.isError ? (
          <Alert severity="error">{extractErrorMessage(exports.error)}</Alert>
        ) : !latest ? (
          <Typography variant="body2">{t('binders.download.none')}</Typography>
        ) : (
          <Stack spacing={1.5}>
            <ExportStatus item={latest} />
            {ready && ready.id !== latest.id && (
              <Typography variant="caption" color="text.secondary">
                {t('binders.download.previous', { date: formatDateTime(ready.finished_at) })}
              </Typography>
            )}
          </Stack>
        )}
        {start.isError && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {extractErrorMessage(start.error)}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('app.close')}</Button>
        <Button onClick={() => start.mutate()} disabled={busy || start.isPending || exports.isPending}>
          {latest ? t('binders.download.prepareToday') : t('binders.download.prepare')}
        </Button>
        {ready && (
          <Button
            variant="contained"
            startIcon={<DownloadIcon />}
            onClick={() => void download(ready)}
            disabled={downloading}
          >
            {downloading ? t('binders.download.downloading') : t('app.download')}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

/**
 * Téléchargement d'un classeur (siège) : les fiches seules, immédiatement, ou le classeur complet
 * avec les décisions officielles.
 */
export function BinderDownload({
  binderKey,
  label,
  variant = 'button',
}: {
  binderKey: string;
  label: string;
  variant?: 'button' | 'icon';
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [official, setOfficial] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const fiches = async () => {
    setAnchor(null);
    setDownloading(true);
    try {
      saveBlob(await fetchBinderPdf(binderKey), `Classeur_${binderKey}.pdf`);
    } catch (e) {
      enqueueSnackbar(extractErrorMessage(e), { variant: 'error' });
    } finally {
      setDownloading(false);
    }
  };

  return (
    <>
      {variant === 'icon' ? (
        <Tooltip title={t('binders.download.tooltip')}>
          <span>
            <IconButton
              size="small"
              onClick={(e) => setAnchor(e.currentTarget)}
              disabled={downloading}
              aria-label={t('binders.download.ariaLabel', { label })}
              sx={{ display: 'flex', mx: 'auto', mt: 0.5 }}
            >
              <DownloadIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      ) : (
        <Button
          variant="outlined"
          startIcon={<DownloadIcon />}
          onClick={(e) => setAnchor(e.currentTarget)}
          disabled={downloading}
        >
          {t('app.download')}
        </Button>
      )}
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => void fiches()}>
          <ListItemText
            primary={t('binders.download.sheetsOnly')}
            secondary={t('binders.download.sheetsOnlyHint')}
          />
        </MenuItem>
        <MenuItem
          onClick={() => {
            setAnchor(null);
            setOfficial(true);
          }}
        >
          <ListItemText
            primary={t('binders.download.withDecisions')}
            secondary={t('binders.download.withDecisionsHint')}
          />
        </MenuItem>
      </Menu>
      <OfficialExportDialog
        binderKey={binderKey}
        label={label}
        open={official}
        onClose={() => setOfficial(false)}
      />
    </>
  );
}
