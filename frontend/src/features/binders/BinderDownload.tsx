import { useState } from 'react';
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
  if (item.status === 'PENDING' || item.status === 'RUNNING') {
    const progress = item.progress_total ? (item.progress_done / item.progress_total) * 100 : 0;
    return (
      <Box>
        <Typography variant="body2" sx={{ mb: 1 }}>
          {item.status === 'PENDING'
            ? 'En attente de préparation…'
            : `Préparation : ${item.progress_done} / ${item.progress_total || '?'} AMM, décisions jointes au fur et à mesure.`}
        </Typography>
        <LinearProgress
          variant={item.progress_total ? 'determinate' : 'indeterminate'}
          value={progress}
          aria-label="Avancement de la préparation"
        />
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          Vous pouvez fermer cette fenêtre : une notification vous prévient quand le classeur est prêt.
        </Typography>
      </Box>
    );
  }
  if (item.status === 'FAILED') {
    return <Alert severity="error">{item.error || 'La préparation a échoué.'}</Alert>;
  }
  return (
    <Alert severity="success" icon={false}>
      <Typography variant="subtitle2">
        Prêt le {formatDateTime(item.finished_at)} · {item.page_count} pages · {formatBytes(item.size_bytes)}
      </Typography>
      <Typography variant="body2">
        {item.decisions} décision{item.decisions > 1 ? 's' : ''} officielle{item.decisions > 1 ? 's' : ''}{' '}
        jointe
        {item.decisions > 1 ? 's' : ''} après leur fiche · {item.without_scan} AMM sans scan (marquées sur la
        fiche)
        {item.unavailable > 0
          ? ` · ${item.unavailable} scan(s) illisible(s), remplacé(s) par une page d'avertissement`
          : ''}
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
      <DialogTitle>{label} — avec les décisions officielles</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Chaque fiche est suivie des scans de la décision d'origine et de ses renouvellements, dans l'ordre
          du classeur papier. Le fichier peut peser plusieurs dizaines de Mo : il est préparé par le serveur.
        </Typography>
        {exports.isPending ? (
          <LinearProgress />
        ) : exports.isError ? (
          <Alert severity="error">{extractErrorMessage(exports.error)}</Alert>
        ) : !latest ? (
          <Typography variant="body2">Aucune préparation pour ce classeur.</Typography>
        ) : (
          <Stack spacing={1.5}>
            <ExportStatus item={latest} />
            {ready && ready.id !== latest.id && (
              <Typography variant="caption" color="text.secondary">
                Version précédente disponible (prête le {formatDateTime(ready.finished_at)}).
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
        <Button onClick={onClose}>Fermer</Button>
        <Button onClick={() => start.mutate()} disabled={busy || start.isPending || exports.isPending}>
          {latest ? 'Préparer avec les données du jour' : 'Préparer le classeur'}
        </Button>
        {ready && (
          <Button
            variant="contained"
            startIcon={<DownloadIcon />}
            onClick={() => void download(ready)}
            disabled={downloading}
          >
            {downloading ? 'Téléchargement…' : 'Télécharger'}
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
        <Tooltip title="Télécharger le classeur">
          <span>
            <IconButton
              size="small"
              onClick={(e) => setAnchor(e.currentTarget)}
              disabled={downloading}
              aria-label={`Télécharger le classeur ${label}`}
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
          Télécharger
        </Button>
      )}
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => void fiches()}>
          <ListItemText
            primary="Fiches du classeur"
            secondary="Immédiat · une page par AMM, tampons et bilan"
          />
        </MenuItem>
        <MenuItem
          onClick={() => {
            setAnchor(null);
            setOfficial(true);
          }}
        >
          <ListItemText
            primary="Avec les décisions officielles"
            secondary="Chaque fiche suivie de ses scans · préparé en arrière-plan"
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
