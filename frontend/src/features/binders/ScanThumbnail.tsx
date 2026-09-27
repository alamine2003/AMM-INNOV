import { useState } from 'react';
import { Box, ButtonBase, CircularProgress, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Document, Page } from 'react-pdf';
import { fetchDocumentBlob } from '@/api/hooks/useDocuments';
import { PdfViewerDialog } from '@/features/documents/PdfViewerDialog';
import { formatDate } from '@/lib/dates';
import { LINE, MUTED } from './paper';

type Scan = { kind: 'image'; src: string } | { kind: 'pdf'; blob: Blob };

/** Sans URL d'objet à libérer : une image devient une URL `data:`, un PDF est passé tel quel. */
async function loadScan(documentId: string): Promise<Scan> {
  const blob = await fetchDocumentBlob(documentId);
  if (!blob.type.startsWith('image/')) return { kind: 'pdf', blob };
  const src = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error('Lecture du scan impossible'));
    reader.readAsDataURL(blob);
  });
  return { kind: 'image', src };
}

/** Miniature de la décision scannée (première page) ; un clic l'ouvre en grand. */
export function ScanThumbnail({
  documentId,
  documentDate,
  title,
  width = 118,
}: {
  documentId: string;
  documentDate: string;
  title: string;
  width?: number;
}) {
  const [open, setOpen] = useState(false);
  const blob = useQuery({
    queryKey: ['binders', 'scan', documentId],
    queryFn: () => loadScan(documentId),
    staleTime: Infinity,
    gcTime: 5 * 60 * 1000,
  });
  const height = Math.round(width * 1.414);
  const scan = blob.data;

  return (
    <>
      <ButtonBase
        onClick={() => setOpen(true)}
        aria-label={`Ouvrir le scan du ${formatDate(documentDate)}`}
        sx={{
          width,
          height,
          flexShrink: 0,
          bgcolor: '#fff',
          border: `1px solid ${LINE}`,
          boxShadow: '2px 3px 8px rgba(0,0,0,0.18)',
          transform: 'rotate(1.5deg)',
          overflow: 'hidden',
          alignItems: 'flex-start',
          transition: 'transform 150ms',
          '&:hover': { transform: 'rotate(0deg) scale(1.04)' },
        }}
      >
        {blob.isError ? (
          <Typography variant="caption" sx={{ color: MUTED, p: 1 }}>
            Scan indisponible
          </Typography>
        ) : !scan ? (
          <Box sx={{ m: 'auto' }}>
            <CircularProgress size={18} />
          </Box>
        ) : scan.kind === 'image' ? (
          <Box
            component="img"
            src={scan.src}
            alt=""
            sx={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <Document file={scan.blob} loading={null} error={null}>
            <Page pageNumber={1} width={width} renderTextLayer={false} renderAnnotationLayer={false} />
          </Document>
        )}
      </ButtonBase>
      <PdfViewerDialog doc={{ id: documentId, title }} open={open} onClose={() => setOpen(false)} />
    </>
  );
}
