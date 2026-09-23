import { useState } from 'react';
import { Alert, Box, Button, Chip, Paper, Stack, Typography } from '@mui/material';
import { extractErrorMessage } from '@/api/client';
import { fetchReviewPointFile, useResolveReviewPoint } from '@/api/hooks/useDossierImports';
import type { DossierReviewPoint } from '@/api/types';
import { formatDate } from '@/lib/dates';
import { ScanViewer, type ScanToView } from './DossierFileViewer';

const closedLabels: Record<string, string> = {
  APPLIED: 'Valeur du scan appliquée',
  IGNORED: 'Ignoré',
};

/**
 * « Points à vérifier plus tard » : écarts entre un scan et la fiche (la fiche a été gardée) et
 * doutes de lecture. Jamais bloquants ; le réglementaire applique la valeur du scan ou ignore.
 */
export function ReviewPointsList({
  points,
  editable,
  showBatch = false,
}: {
  points: DossierReviewPoint[];
  editable: boolean;
  /** Fiche AMM : rappelle de quel dossier vient chaque point. */
  showBatch?: boolean;
}) {
  const resolve = useResolveReviewPoint();
  const [viewing, setViewing] = useState<ScanToView | null>(null);
  const open = points.filter((point) => point.status === 'OPEN');
  if (!points.length) return null;
  return (
    <Paper variant="outlined" sx={{ p: 3 }} component="section" aria-label="Points à vérifier plus tard">
      <Typography variant="h6">Points à vérifier plus tard ({open.length})</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Rien n’est bloqué : la valeur de la fiche a été gardée et les scans sont rangés. Vérifiez sur le scan
        quand vous le pouvez.
      </Typography>
      {resolve.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {extractErrorMessage(resolve.error)}
        </Alert>
      )}
      <Stack spacing={1.5}>
        {points.map((point) => (
          <Box
            key={point.id}
            data-testid={`point-${point.id}`}
            sx={{ borderLeft: 3, borderColor: point.status === 'OPEN' ? 'warning.main' : 'divider', pl: 1.5 }}
          >
            <Typography variant="body2">{point.message}</Typography>
            {showBatch && (
              <Typography variant="caption" color="text.secondary" display="block">
                Dossier « {point.batch_name} » · {formatDate(point.created_at)}
              </Typography>
            )}
            <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center" sx={{ mt: 0.5 }}>
              {point.proof_file_id && (
                <Button
                  size="small"
                  onClick={() =>
                    setViewing({
                      id: point.id,
                      name: point.proof_name ?? 'Scan',
                      contentType: point.proof_content_type ?? 'application/pdf',
                      load: () => fetchReviewPointFile(point.id),
                    })
                  }
                >
                  Voir le scan
                </Button>
              )}
              {point.status === 'OPEN' && editable ? (
                <>
                  {point.applicable && (
                    <Button
                      size="small"
                      variant="outlined"
                      disabled={resolve.isPending}
                      onClick={() => resolve.mutate({ id: point.id, action: 'apply' })}
                    >
                      Appliquer la valeur du scan
                    </Button>
                  )}
                  <Button
                    size="small"
                    disabled={resolve.isPending}
                    onClick={() => resolve.mutate({ id: point.id, action: 'ignore' })}
                  >
                    Ignorer
                  </Button>
                </>
              ) : (
                point.status !== 'OPEN' && (
                  <Chip
                    size="small"
                    variant="outlined"
                    label={`${closedLabels[point.status]}${point.resolved_by_email ? ` · ${point.resolved_by_email}` : ''}`}
                  />
                )
              )}
            </Stack>
          </Box>
        ))}
      </Stack>
      <ScanViewer scan={viewing} onClose={() => setViewing(null)} />
    </Paper>
  );
}
