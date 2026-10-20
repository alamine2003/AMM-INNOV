import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material';
import DescriptionIcon from '@mui/icons-material/Description';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import type { BinderChronologyDocument, BinderChronologyEntry, BinderPage } from '@/api/types';
import { PdfViewerDialog } from '@/features/documents/PdfViewerDialog';
import { formatDate } from '@/lib/dates';
import { ScanImportButton, ScanImportStatus, type usePageScanImport } from './PageScanImport';
import { INK, MUTED } from './paper';

type ScanImport = ReturnType<typeof usePageScanImport>;

const KIND_COLORS: Record<BinderChronologyEntry['kind'], string> = {
  pending: '#ef6c00',
  renewal: '#1565c0',
  origin: '#2e7d32',
  closed: '#757575',
  gap: '#c62828',
};

/** Nombre de manques sur la page (décisions non scannées, dates, trous de validité…). */
export function chronologyIssues(page: Pick<BinderPage, 'chronology'>): number {
  return page.chronology.reduce((total, entry) => total + entry.issues.length, 0);
}

function period(entry: BinderChronologyEntry): string {
  if (entry.kind === 'pending') {
    return entry.filing_date ? `déposé le ${formatDate(entry.filing_date)}` : 'dépôt non daté';
  }
  if (!entry.start_date && !entry.end_date) return 'dates inconnues';
  return `du ${entry.start_date ? formatDate(entry.start_date) : '?'} au ${
    entry.end_date ? formatDate(entry.end_date) : '?'
  }`;
}

/**
 * Chronologie d'une AMM, de la décision la plus récente à l'AMM d'origine : pour chaque période, ses
 * décisions scannées, ses autres pièces (récépissés, courriers) et ce qui manque, avec le moyen de le
 * régler (importer le scan, corriger sur le classeur papier).
 */
export function ChronologyDialog({
  page,
  open,
  onClose,
  scanImport,
}: {
  page: BinderPage;
  open: boolean;
  onClose: () => void;
  scanImport: ScanImport;
}) {
  const [viewed, setViewed] = useState<BinderChronologyDocument | null>(null);
  const issues = chronologyIssues(page);
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="chronology-dialog">
      <DialogTitle sx={{ pb: 0.5 }}>
        {page.product_name}
        <Typography variant="body2" sx={{ color: MUTED }}>
          Chronologie : de la décision la plus récente à l'AMM d'origine ·{' '}
          {issues ? `${issues} manque${issues > 1 ? 's' : ''} à régler` : 'rien ne manque'}
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={0}>
          {page.chronology.map((entry, index) => {
            const color = KIND_COLORS[entry.kind];
            const last = index === page.chronology.length - 1;
            return (
              <Stack
                key={`${entry.kind}-${entry.renewal_id ?? index}`}
                direction="row"
                spacing={1.5}
                data-testid={`chronology-${entry.kind}`}
              >
                {/* Fil chronologique : un point par période, pointillé rouge pour un trou de validité. */}
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 16 }}>
                  <Box
                    sx={{
                      mt: 0.75,
                      width: 12,
                      height: 12,
                      borderRadius: '50%',
                      bgcolor: entry.kind === 'gap' ? 'transparent' : color,
                      border: `2px solid ${color}`,
                    }}
                  />
                  {!last && (
                    <Box
                      sx={{
                        flex: 1,
                        borderLeft: `2px ${entry.kind === 'gap' ? 'dashed' : 'solid'} ${
                          entry.kind === 'gap' ? color : '#cfd8dc'
                        }`,
                      }}
                    />
                  )}
                </Box>
                <Box sx={{ flex: 1, pb: 2 }}>
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline', flexWrap: 'wrap' }}>
                    <Typography sx={{ fontWeight: 700, color }}>{entry.label}</Typography>
                    {entry.number && (
                      <Typography sx={{ fontSize: 13, color: INK }}>n° {entry.number}</Typography>
                    )}
                    <Typography sx={{ fontSize: 13, color: MUTED }}>{period(entry)}</Typography>
                    {entry.kind === 'closed' && entry.workflow_label && (
                      <Chip size="small" label={entry.workflow_label} />
                    )}
                    {entry.kind === 'pending' && entry.workflow_label && (
                      <Chip size="small" color="warning" variant="outlined" label={entry.workflow_label} />
                    )}
                  </Stack>
                  {!!(entry.decisions?.length || entry.others?.length) && (
                    <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 0.75, mt: 0.75 }}>
                      {(entry.decisions ?? []).map((doc) => (
                        <Chip
                          key={doc.document_id}
                          icon={<DescriptionIcon />}
                          color="primary"
                          label={`Décision du ${formatDate(doc.document_date)}${
                            doc.page_count ? ` · ${doc.page_count} p.` : ''
                          }`}
                          onClick={() => setViewed(doc)}
                        />
                      ))}
                      {(entry.others ?? []).map((doc) => (
                        <Chip
                          key={doc.document_id}
                          variant="outlined"
                          label={`${doc.kind_label} du ${formatDate(doc.document_date)}`}
                          onClick={() => setViewed(doc)}
                        />
                      ))}
                    </Stack>
                  )}
                  {entry.issues.map((issue) => (
                    <Alert
                      key={issue.code}
                      severity={issue.code === 'gap' || issue.code === 'no_scan' ? 'error' : 'warning'}
                      icon={<ReportProblemIcon fontSize="small" />}
                      sx={{ mt: 0.75, py: 0, fontSize: 13 }}
                      data-testid={`issue-${issue.code}`}
                    >
                      {issue.message}
                    </Alert>
                  ))}
                </Box>
              </Stack>
            );
          })}
        </Stack>
        <ScanImportStatus scanImport={scanImport} />
      </DialogContent>
      <DialogActions sx={{ justifyContent: 'space-between' }}>
        <Typography variant="caption" sx={{ color: MUTED, pl: 1 }}>
          Un scan importé est lu (n° et dates) puis rangé sur la bonne période.
        </Typography>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Box sx={{ mt: -1 }}>
            <ScanImportButton scanImport={scanImport} hasScan={page.decision_count > 0} />
          </Box>
          <Button onClick={onClose}>Fermer</Button>
        </Stack>
      </DialogActions>
      <PdfViewerDialog
        doc={viewed ? { id: viewed.document_id, title: viewed.title || page.product_name } : null}
        open={!!viewed}
        onClose={() => setViewed(null)}
      />
    </Dialog>
  );
}
