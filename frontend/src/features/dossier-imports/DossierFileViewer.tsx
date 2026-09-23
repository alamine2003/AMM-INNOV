import { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material';
import { Document, Page } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { fetchDossierFile } from '@/api/hooks/useDossierImports';
import type { DossierImportFile } from '@/api/types';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { saveBlob } from '@/lib/download';

/** Un scan à afficher : son nom, son type et comment le charger (lot ou point à vérifier). */
export interface ScanToView {
  id: string;
  name: string;
  contentType: string;
  load: () => Promise<Blob>;
}

function ViewerContent({ file }: { file: ScanToView }) {
  const [loaded, setLoaded] = useState<{ blob: Blob; url: string } | null>(null);
  const [error, setError] = useState<unknown>();
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | undefined;
    file
      .load()
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setLoaded({ blob, url: objectUrl });
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // Un scan se charge une fois par ouverture (clé de rendu = identifiant du scan).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.id]);
  return (
    <>
      <DialogContent dividers>
        {!!error && <ErrorBlock error={error} />}
        {!error && !loaded && <LoadingBlock />}
        {loaded && (
          <Box sx={{ textAlign: 'center', overflow: 'auto' }}>
            {file.contentType.startsWith('image/') ? (
              <Box
                component="img"
                src={loaded.url}
                alt={file.name}
                sx={{ maxWidth: '100%', height: 'auto' }}
              />
            ) : (
              <>
                <Stack direction="row" justifyContent="center" spacing={2} alignItems="center" sx={{ mb: 2 }}>
                  <Button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
                    Page précédente
                  </Button>
                  <Typography>
                    {page} / {pageCount || '…'}
                  </Typography>
                  <Button
                    disabled={!pageCount || page >= pageCount}
                    onClick={() => setPage((value) => value + 1)}
                  >
                    Page suivante
                  </Button>
                </Stack>
                <Document
                  file={loaded.url}
                  loading={<LoadingBlock />}
                  onLoadSuccess={({ numPages }) => setPageCount(numPages)}
                  onLoadError={setError}
                >
                  <Page pageNumber={page} scale={1.1} />
                </Document>
              </>
            )}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button
          disabled={!loaded}
          onClick={() => loaded && saveBlob(loaded.blob, file.name.split('/').at(-1) || 'document')}
        >
          Télécharger le document
        </Button>
      </DialogActions>
    </>
  );
}

export function ScanViewer({ scan, onClose }: { scan: ScanToView | null; onClose: () => void }) {
  return (
    <Dialog open={!!scan} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography component="span" sx={{ flex: 1, overflowWrap: 'anywhere' }}>
          {scan?.name}
        </Typography>
        <Button onClick={onClose}>Fermer</Button>
      </DialogTitle>
      {scan && <ViewerContent key={scan.id} file={scan} />}
    </Dialog>
  );
}

/** Scan déposé dans un lot, diffusé depuis le stockage (message clair si le fichier est perdu). */
export function DossierFileViewer({
  batchId,
  file,
  onClose,
}: {
  batchId: string;
  file: DossierImportFile | null;
  onClose: () => void;
}) {
  return (
    <ScanViewer
      scan={
        file && {
          id: file.id,
          name: file.relative_path,
          contentType: file.content_type,
          load: () => fetchDossierFile(batchId, file.id),
        }
      }
      onClose={onClose}
    />
  );
}
