import { useEffect, useState } from 'react';
import { AppBar, Box, Dialog, IconButton, Toolbar, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import ZoomOutIcon from '@mui/icons-material/ZoomOut';
import NavigateBeforeIcon from '@mui/icons-material/NavigateBefore';
import NavigateNextIcon from '@mui/icons-material/NavigateNext';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import DownloadIcon from '@mui/icons-material/Download';
import { Document, Page } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { useTranslation } from 'react-i18next';
import { fetchDocumentBlob } from '@/api/hooks/useDocuments';
import type { AmmDocument } from '@/api/types';
import { saveBlob } from '@/lib/download';
import { LoadingBlock, ErrorBlock } from '@/components/QueryState';

interface Loaded {
  blob: Blob;
  url: string;
}

/** Contenu de la visionneuse ; remonté avec une clé par document pour repartir d'un état neuf. */
function PdfViewerContent({
  doc,
  onClose,
  fileName,
}: {
  doc: AmmDocument;
  onClose: () => void;
  fileName?: string;
}) {
  const { t } = useTranslation();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [numPages, setNumPages] = useState(0);
  const [page, setPage] = useState(1);
  const [scale, setScale] = useState(1.1);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    fetchDocumentBlob(doc.id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setLoaded({ blob, url: objectUrl });
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [doc.id]);

  return (
    <>
      <AppBar position="relative" color="default">
        <Toolbar sx={{ gap: 0.5 }}>
          <Typography variant="subtitle1" sx={{ flexGrow: 1 }} noWrap>
            {doc.title}
          </Typography>
          <IconButton
            onClick={() => setScale((s) => Math.max(0.5, s - 0.2))}
            aria-label={t('documents.viewer.zoomOut')}
          >
            <ZoomOutIcon />
          </IconButton>
          <Typography variant="body2" sx={{ minWidth: 48, textAlign: 'center' }}>
            {Math.round(scale * 100)} %
          </Typography>
          <IconButton
            onClick={() => setScale((s) => Math.min(3, s + 0.2))}
            aria-label={t('documents.viewer.zoomIn')}
          >
            <ZoomInIcon />
          </IconButton>
          <IconButton
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            aria-label={t('documents.viewer.prev')}
          >
            <NavigateBeforeIcon />
          </IconButton>
          <Typography variant="body2" sx={{ minWidth: 90, textAlign: 'center' }}>
            {t('documents.viewer.page', { page, total: numPages || '?' })}
          </Typography>
          <IconButton
            onClick={() => setPage((p) => Math.min(numPages || 1, p + 1))}
            disabled={page >= numPages}
            aria-label={t('documents.viewer.next')}
          >
            <NavigateNextIcon />
          </IconButton>
          <IconButton
            onClick={() => loaded && window.open(loaded.url, '_blank', 'noopener')}
            disabled={!loaded}
            aria-label={t('documents.openNewTab')}
          >
            <OpenInNewIcon />
          </IconButton>
          <IconButton
            onClick={() => loaded && saveBlob(loaded.blob, fileName ?? `${doc.title || 'document'}.pdf`)}
            disabled={!loaded}
            aria-label={t('app.download')}
          >
            <DownloadIcon />
          </IconButton>
          <IconButton edge="end" onClick={onClose} aria-label={t('app.close')}>
            <CloseIcon />
          </IconButton>
        </Toolbar>
      </AppBar>
      <Box
        sx={{
          flexGrow: 1,
          overflow: 'auto',
          bgcolor: 'grey.300',
          display: 'flex',
          justifyContent: 'center',
          p: 2,
        }}
      >
        {error ? <ErrorBlock error={error} /> : null}
        {!error && !loaded ? <LoadingBlock /> : null}
        {loaded ? (
          <Document
            file={loaded.url}
            onLoadSuccess={(pdf) => setNumPages(pdf.numPages)}
            onLoadError={(e) => setError(e)}
            loading={<LoadingBlock />}
            error={<ErrorBlock error={new Error(t('documents.viewer.error'))} />}
          >
            <Page pageNumber={page} scale={scale} renderTextLayer renderAnnotationLayer />
          </Document>
        ) : null}
      </Box>
    </>
  );
}

export function PdfViewerDialog({
  doc,
  open,
  onClose,
  fileName,
}: {
  doc: AmmDocument | null;
  open: boolean;
  onClose: () => void;
  fileName?: string;
}) {
  return (
    <Dialog open={open && !!doc} onClose={onClose} fullScreen data-testid="pdf-viewer">
      {doc && <PdfViewerContent key={doc.id} doc={doc} onClose={onClose} fileName={fileName} />}
    </Dialog>
  );
}
