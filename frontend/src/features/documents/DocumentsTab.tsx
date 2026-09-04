import { useState } from 'react';
import { Box, Button, Stack } from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import FolderZipIcon from '@mui/icons-material/FolderZip';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import {
  documentFileName,
  fetchAmmArchive,
  fetchDocumentBlob,
  useAmmDocumentsByPeriod,
  useDeleteDocument,
} from '@/api/hooks/useDocuments';
import { useRenewals } from '@/api/hooks/useRenewals';
import type { Amm, AmmDocument } from '@/api/types';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { saveBlob } from '@/lib/download';
import { extractErrorMessage } from '@/api/client';
import { isAdmin, useAuthStore } from '@/features/auth/authStore';
import { DocumentTimeline } from './DocumentTimeline';
import { UploadDocumentDialog } from './UploadDocumentDialog';
import { PdfViewerDialog } from './PdfViewerDialog';

export function DocumentsTab({ amm, editable }: { amm: Amm; editable: boolean }) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const user = useAuthStore((s) => s.user);
  const periods = useAmmDocumentsByPeriod(amm.id);
  const renewals = useRenewals(amm.id);
  const remove = useDeleteDocument(amm.id);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [replaceTarget, setReplaceTarget] = useState<AmmDocument | null>(null);
  const [viewing, setViewing] = useState<AmmDocument | null>(null);
  const [deleting, setDeleting] = useState<AmmDocument | null>(null);
  const [zipping, setZipping] = useState(false);

  if (periods.isPending) return <LoadingBlock />;
  if (periods.isError) return <ErrorBlock error={periods.error} onRetry={() => periods.refetch()} />;

  const allDocs = periods.data.flatMap((p) => p.documents);
  const fileName = (d: AmmDocument) => documentFileName(d, amm.country_iso2, amm.product_name);

  const download = async (d: AmmDocument) => {
    try {
      saveBlob(await fetchDocumentBlob(d.id, true), fileName(d));
    } catch (e) {
      enqueueSnackbar(extractErrorMessage(e), { variant: 'error' });
    }
  };
  const downloadZip = async () => {
    setZipping(true);
    try {
      saveBlob(
        await fetchAmmArchive(amm.id),
        `${amm.country_iso2}_${amm.product_name}_dossier.zip`.replace(/\s+/g, '_'),
      );
    } catch (e) {
      enqueueSnackbar(extractErrorMessage(e), { variant: 'error' });
    } finally {
      setZipping(false);
    }
  };

  return (
    <Box>
      <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Button
          variant="outlined"
          startIcon={<FolderZipIcon />}
          onClick={downloadZip}
          disabled={zipping || allDocs.length === 0}
        >
          {t('documents.downloadZip')}
        </Button>
        {editable && (
          <Button
            variant="contained"
            startIcon={<UploadFileIcon />}
            onClick={() => setUploadOpen(true)}
            data-testid="doc-upload-open"
          >
            {t('documents.upload')}
          </Button>
        )}
      </Stack>
      {allDocs.length === 0 && periods.data.length === 0 ? (
        <EmptyBlock text={t('documents.empty')} />
      ) : (
        <DocumentTimeline
          periods={periods.data}
          onView={setViewing}
          onDownload={download}
          onReplace={(d) => {
            setReplaceTarget(d);
            setUploadOpen(true);
          }}
          onDelete={setDeleting}
          canEdit={editable}
          canDelete={isAdmin(user)}
        />
      )}
      <UploadDocumentDialog
        amm={amm}
        renewals={renewals.data ?? []}
        existing={allDocs}
        replaceTarget={replaceTarget}
        open={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
          setReplaceTarget(null);
        }}
      />
      <PdfViewerDialog
        doc={viewing}
        open={!!viewing}
        onClose={() => setViewing(null)}
        fileName={viewing ? fileName(viewing) : undefined}
      />
      <ConfirmDialog
        open={!!deleting}
        title={t('app.confirmDelete')}
        text={t('documents.deleteConfirm')}
        onClose={() => setDeleting(null)}
        loading={remove.isPending}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => {
              enqueueSnackbar(t('documents.deleted'), { variant: 'success' });
              setDeleting(null);
            },
            onError: (e) => enqueueSnackbar(extractErrorMessage(e), { variant: 'error' }),
          })
        }
      />
    </Box>
  );
}
