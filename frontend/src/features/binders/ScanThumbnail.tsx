import { useState } from 'react';
import { Box, ButtonBase, CircularProgress, Typography } from '@mui/material';
import AttachFileIcon from '@mui/icons-material/AttachFile';
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

/**
 * Miniature de la décision scannée (première page) ; un clic l'ouvre en grand.
 *
 * `stack` : nombre de décisions plus anciennes agrafées dessous (origine → renouvellements), dessinées
 * en feuilles décalées ; la plus récente reste visible en haut. `onOpen` remplace l'ouverture du scan
 * (la page ouvre alors la chronologie de l'AMM).
 */
export function ScanThumbnail({
  documentId,
  documentDate,
  title,
  width = 118,
  stack = 0,
  onOpen,
  label,
}: {
  documentId: string;
  documentDate: string;
  title: string;
  width?: number;
  stack?: number;
  onOpen?: () => void;
  label?: string;
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

  const behind = Math.min(stack, 3);
  return (
    <Box sx={{ position: 'relative', flexShrink: 0, mr: `${behind * 4}px`, mb: `${behind * 3}px` }}>
      {/* Décisions plus anciennes, agrafées sous la plus récente. */}
      {Array.from({ length: behind }, (_, i) => behind - i).map((depth) => (
        <Box
          key={depth}
          aria-hidden
          data-testid="scan-stack-sheet"
          sx={{
            position: 'absolute',
            inset: 0,
            width,
            height,
            bgcolor: '#fbfaf6',
            border: `1px solid ${LINE}`,
            boxShadow: '1px 2px 4px rgba(0,0,0,0.12)',
            transform: `translate(${depth * 4}px, ${depth * 3}px) rotate(${depth % 2 ? -2 : 3}deg)`,
          }}
        />
      ))}
      {/* Trombone : le scan est agrafé à la fiche, comme dans le classeur. */}
      <AttachFileIcon
        aria-hidden
        sx={{
          position: 'absolute',
          top: -12,
          left: 14,
          zIndex: 1,
          fontSize: 30,
          color: '#8a94a6',
          transform: 'rotate(38deg)',
          filter: 'drop-shadow(1px 1px 1px rgba(0,0,0,0.3))',
        }}
      />
      <ButtonBase
        onClick={() => (onOpen ? onOpen() : setOpen(true))}
        aria-label={label ?? `Ouvrir le scan du ${formatDate(documentDate)}`}
        sx={{
          position: 'relative',
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
      {stack > 0 && (
        <Box
          aria-hidden
          sx={{
            position: 'absolute',
            right: -8,
            bottom: -8,
            zIndex: 2,
            minWidth: 22,
            height: 22,
            px: 0.5,
            borderRadius: 11,
            bgcolor: '#37474f',
            color: '#fff',
            fontSize: 12,
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {stack + 1}
        </Box>
      )}
      <PdfViewerDialog doc={{ id: documentId, title }} open={open} onClose={() => setOpen(false)} />
    </Box>
  );
}
