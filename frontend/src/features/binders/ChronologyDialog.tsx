import { extractErrorMessage } from '@/api/client';
import { useChronologyEdits } from '@/api/hooks/useBinders';
import type { BinderChronologyDocument, BinderPage } from '@/api/types';
import { useCan } from '@/features/auth/authStore';
import { PdfViewerDialog } from '@/features/documents/PdfViewerDialog';
import { formatDate } from '@/lib/dates';
import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DescriptionIcon from '@mui/icons-material/Description';
import EditIcon from '@mui/icons-material/Edit';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { AddDocumentForm, CancelRenewalForm, DocumentForm, PeriodForm } from './ChronologyForms';
import {
  type Editing,
  KIND_COLORS,
  type ScanImport,
  chronologyIssues,
  period,
  periodOf,
} from './chronologyShared';
import { ScanImportButton, ScanImportStatus } from './PageScanImport';
import { INK, MUTED } from './paper';
/**
 * Chronologie d'une AMM, de la décision la plus récente à l'AMM d'origine : pour chaque période, ses
 * décisions scannées, ses autres pièces (récépissés, courriers) et ce qui manque. Tout s'y corrige :
 * n° et dates d'une période, renouvellement en trop, date / type / période d'une pièce, pièce retirée
 * ou ajoutée sur la bonne période. La page du classeur se met à jour aussitôt.
 */
export function ChronologyDialog({
  page,
  binderKey,
  open,
  onClose,
  scanImport,
  years = 5,
}: {
  page: BinderPage;
  binderKey: string;
  open: boolean;
  onClose: () => void;
  scanImport: ScanImport;
  /** Durée de validité du pays (années) : la fin d'une période corrigée en découle. */
  years?: number;
}) {
  const [viewed, setViewed] = useState<BinderChronologyDocument | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const edits = useChronologyEdits(binderKey, page.amm_id);
  const canRemove = useCan('binder.remove_passage');
  const canRemovePiece = useCan('binder.remove_piece');
  const issues = chronologyIssues(page);
  const periods = page.chronology.filter((entry) => entry.kind !== 'gap');
  const options = periods.map((entry) => ({ value: periodOf(entry), label: entry.label }));
  const failed = Object.values(edits).find((mutation) => mutation.isError);
  const close = () => {
    setEditing(null);
    onClose();
  };
  const toggle = (next: Editing) => {
    Object.values(edits).forEach((mutation) => mutation.reset());
    setEditing(next);
  };
  const done = () => setEditing(null);

  return (
    <Dialog open={open} onClose={close} maxWidth="md" fullWidth data-testid="chronology-dialog">
      <DialogTitle sx={{ pb: 0.5 }}>
        {page.product_name}
        <Typography variant="body2" sx={{ color: MUTED }}>
          Chronologie : de la décision la plus récente à l'AMM d'origine ·{' '}
          {issues ? `${issues} manque${issues > 1 ? 's' : ''} à régler` : 'rien ne manque'}
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        {failed && (
          <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => failed.reset()}>
            {extractErrorMessage(failed.error)}
          </Alert>
        )}
        <Stack spacing={0}>
          {page.chronology.map((entry, index) => {
            const color = entry.ignored ? MUTED : KIND_COLORS[entry.kind];
            const last = index === page.chronology.length - 1;
            const here = entry.kind === 'gap' ? null : periodOf(entry);
            const openHere = editing && here !== null && editing.period === here ? editing : null;
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
                <Box sx={{ flex: 1, pb: 2, minWidth: 0 }}>
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
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
                    {here !== null && (
                      <Box sx={{ ml: 'auto !important', display: 'flex' }}>
                        <Tooltip title="Corriger le n° et les dates">
                          <IconButton
                            size="small"
                            aria-label={`Corriger ${entry.label}`}
                            onClick={() => toggle({ type: 'period', period: here })}
                          >
                            <EditIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Ajouter une pièce sur cette période">
                          <IconButton
                            size="small"
                            aria-label={`Ajouter une pièce — ${entry.label}`}
                            onClick={() => toggle({ type: 'add', period: here })}
                          >
                            <AddIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        {canRemove && entry.renewal_id && (
                          <Tooltip title="Supprimer ce passage (il n'existe pas) : les scans restent">
                            <IconButton
                              size="small"
                              color="error"
                              aria-label={`Supprimer ${entry.label}`}
                              onClick={() => toggle({ type: 'cancel', period: entry.renewal_id! })}
                            >
                              <DeleteOutlineIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        )}
                      </Box>
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
                          deleteIcon={
                            <Tooltip title="Corriger la date, le type ou la période">
                              <EditIcon
                                aria-label={`Corriger la décision du ${formatDate(doc.document_date)}`}
                              />
                            </Tooltip>
                          }
                          onDelete={() => toggle({ type: 'document', period: here!, doc })}
                        />
                      ))}
                      {(entry.others ?? []).map((doc) => (
                        <Chip
                          key={doc.document_id}
                          variant="outlined"
                          label={`${doc.kind_label} du ${formatDate(doc.document_date)}`}
                          onClick={() => setViewed(doc)}
                          deleteIcon={
                            <Tooltip title="Corriger la date, le type ou la période">
                              <EditIcon
                                aria-label={`Corriger ${doc.kind_label} du ${formatDate(doc.document_date)}`}
                              />
                            </Tooltip>
                          }
                          onDelete={() => toggle({ type: 'document', period: here!, doc })}
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
                  {entry.kind === 'gap' && entry.start_date && entry.end_date && (
                    <Button
                      size="small"
                      sx={{ mt: 0.5 }}
                      disabled={edits.ignoreGap.isPending}
                      data-testid={entry.ignored ? 'gap-restore' : 'gap-ignore'}
                      onClick={() =>
                        edits.ignoreGap.mutate({
                          start_date: entry.start_date!,
                          end_date: entry.end_date!,
                          ignored: !entry.ignored,
                        })
                      }
                    >
                      {entry.ignored
                        ? 'Ne plus ignorer ce trou'
                        : "Ignorer : il n'y a pas eu de renouvellement sur cette période"}
                    </Button>
                  )}
                  {openHere?.type === 'period' && (
                    <PeriodForm entry={entry} edits={edits} years={years} onDone={done} />
                  )}
                  {openHere?.type === 'add' && <AddDocumentForm entry={entry} edits={edits} onDone={done} />}
                  {openHere?.type === 'cancel' && (
                    <CancelRenewalForm entry={entry} options={options} edits={edits} onDone={done} />
                  )}
                  {openHere?.type === 'document' && (
                    <DocumentForm
                      key={openHere.doc.document_id}
                      doc={openHere.doc}
                      current={here!}
                      options={options}
                      edits={edits}
                      canRemove={canRemovePiece}
                      onDone={done}
                    />
                  )}
                </Box>
              </Stack>
            );
          })}
        </Stack>
        <ScanImportStatus scanImport={scanImport} />
      </DialogContent>
      <DialogActions sx={{ justifyContent: 'space-between' }}>
        <Typography variant="caption" sx={{ color: MUTED, pl: 1 }}>
          ✎ corrige une période ou une pièce · + ajoute une pièce à la date saisie · un scan importé est lu
          (n° et dates) puis rangé automatiquement.
        </Typography>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Box sx={{ mt: -1 }}>
            <ScanImportButton scanImport={scanImport} hasScan={page.decision_count > 0} />
          </Box>
          <Button onClick={close}>Fermer</Button>
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
