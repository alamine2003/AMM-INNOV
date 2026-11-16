import { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, CircularProgress, Link as MuiLink, Typography } from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import { useQueryClient } from '@tanstack/react-query';
import { Trans, useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { extractErrorMessage } from '@/api/client';
import { binderKeys, useImportPageScan } from '@/api/hooks/useBinders';
import { useDossierImport } from '@/api/hooks/useDossierImports';
import { hasSummary } from '@/api/types';

export const SCAN_ACCEPT = 'application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png';

/**
 * Scan importé depuis une page : envoyé comme un dossier rangé sur cette AMM, puis suivi jusqu'au
 * rangement. La page se met à jour (miniature, n° et dates relus) dès que le scan est rangé.
 */
export function usePageScanImport(binderKey: string, ammId: string) {
  const client = useQueryClient();
  const upload = useImportPageScan(binderKey);
  const [batchId, setBatchId] = useState<string | null>(null);
  const batch = useDossierImport(batchId ?? undefined);
  const status = batch.data?.status;

  useEffect(() => {
    if (status && !['PENDING', 'RUNNING'].includes(status)) {
      void client.invalidateQueries({ queryKey: binderKeys.detail(binderKey) });
      void client.invalidateQueries({ queryKey: binderKeys.shelf });
      void client.invalidateQueries({ queryKey: ['amms'] });
    }
  }, [client, binderKey, status]);

  const start = (files: File[]) => {
    const scans = files.filter(
      (file) =>
        /\.(pdf|jpe?g|png)$/i.test(file.name) ||
        ['application/pdf', 'image/jpeg', 'image/png'].includes(file.type),
    );
    if (!scans.length) return;
    upload.mutate({ amm: ammId, files: scans }, { onSuccess: (result) => setBatchId(result.batch_id) });
  };

  const busy = upload.isPending || status === 'PENDING' || status === 'RUNNING';
  return { start, upload, batch: batch.data, batchId, busy };
}

type ScanImport = ReturnType<typeof usePageScanImport>;

export function ScanImportButton({ scanImport, hasScan }: { scanImport: ScanImport; hasScan: boolean }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <Button
        size="small"
        variant={hasScan ? 'text' : 'contained'}
        color={hasScan ? 'primary' : 'error'}
        startIcon={scanImport.busy ? <CircularProgress size={14} color="inherit" /> : <UploadFileIcon />}
        onClick={() => input.current?.click()}
        disabled={scanImport.busy}
        sx={{ mt: 1 }}
      >
        {hasScan ? t('binders.scan.add') : t('binders.scan.import')}
      </Button>
      <input
        ref={input}
        type="file"
        hidden
        multiple
        accept={SCAN_ACCEPT}
        aria-label={t('binders.scan.inputLabel')}
        onChange={(e) => {
          scanImport.start(Array.from(e.target.files ?? []));
          e.target.value = '';
        }}
      />
    </>
  );
}

export function ScanImportStatus({ scanImport }: { scanImport: ScanImport }) {
  const { t } = useTranslation();
  const { upload, batch, batchId } = scanImport;
  if (upload.isError) {
    return (
      <Alert severity="error" sx={{ mt: 1.5 }}>
        {extractErrorMessage(upload.error)}
      </Alert>
    );
  }
  if (!batchId) return null;
  const link = <MuiLink component={Link} to={`/dossier-imports/${batchId}`} />;
  if (!batch || batch.status === 'PENDING' || batch.status === 'RUNNING') {
    return (
      <Alert severity="info" icon={<CircularProgress size={18} />} sx={{ mt: 1.5 }}>
        {t('binders.scan.reading')}
      </Alert>
    );
  }
  if (batch.status === 'APPLIED') {
    const lines = hasSummary(batch.summary) ? batch.summary.lines.slice(0, 4) : [];
    return (
      <Alert severity="success" sx={{ mt: 1.5 }}>
        <Typography variant="subtitle2">
          <Trans i18nKey="binders.scan.stored" components={{ link }} />
        </Typography>
        {lines.map((line) => (
          <Box key={line} component="div" sx={{ fontSize: 13 }}>
            {line}
          </Box>
        ))}
      </Alert>
    );
  }
  return (
    <Alert severity="warning" sx={{ mt: 1.5 }}>
      {batch.status === 'FAILED' ? (
        <Trans
          i18nKey="binders.scan.failed"
          values={{ error: batch.error || t('binders.scan.unknownError') }}
          components={{ link }}
        />
      ) : (
        <Trans i18nKey="binders.scan.needsReview" components={{ link }} />
      )}
    </Alert>
  );
}
