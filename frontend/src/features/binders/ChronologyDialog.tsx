import { useRef, useState, type ReactNode } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DescriptionIcon from '@mui/icons-material/Description';
import EditIcon from '@mui/icons-material/Edit';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import { extractErrorMessage } from '@/api/client';
import { useCurrentUser } from '@/api/hooks/useAuth';
import { useChronologyEdits, type ChronologyPeriod, type PeriodValues } from '@/api/hooks/useBinders';
import type {
  BinderChronologyDocument,
  BinderChronologyEntry,
  BinderDocumentKind,
  BinderPage,
} from '@/api/types';
import { PdfViewerDialog } from '@/features/documents/PdfViewerDialog';
import { formatDate } from '@/lib/dates';
import { SCAN_ACCEPT, ScanImportButton, ScanImportStatus, type usePageScanImport } from './PageScanImport';
import { INK, LINE, MUTED } from './paper';

type ScanImport = ReturnType<typeof usePageScanImport>;
type Edits = ReturnType<typeof useChronologyEdits>;

const KIND_COLORS: Record<BinderChronologyEntry['kind'], string> = {
  pending: '#ef6c00',
  renewal: '#1565c0',
  origin: '#2e7d32',
  closed: '#757575',
  gap: '#c62828',
};

const DOCUMENT_KINDS: { value: BinderDocumentKind; label: string }[] = [
  { value: 'AMM', label: 'Décision (AMM)' },
  { value: 'RECEPISSE', label: 'Récépissé de dépôt' },
  { value: 'COURRIER', label: "Courrier de l'autorité" },
  { value: 'AUTRE', label: 'Autre' },
];

/** Ce qui est ouvert en édition dans la chronologie : une seule chose à la fois. */
type Editing =
  | { type: 'period'; period: ChronologyPeriod }
  | { type: 'cancel'; period: string }
  | { type: 'add'; period: ChronologyPeriod }
  | { type: 'document'; period: ChronologyPeriod; doc: BinderChronologyDocument }
  | null;

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

const periodOf = (entry: BinderChronologyEntry): ChronologyPeriod => entry.renewal_id ?? 'origin';

/** Petit formulaire posé sous une période, dans le fil de la chronologie. */
function EditPanel({
  title,
  children,
  onSave,
  onCancel,
  saveLabel = 'Enregistrer',
  saveColor = 'primary',
  busy,
  extra,
}: {
  title: string;
  children: ReactNode;
  onSave: () => void;
  onCancel: () => void;
  saveLabel?: string;
  saveColor?: 'primary' | 'error';
  busy: boolean;
  extra?: ReactNode;
}) {
  return (
    <Box
      component="form"
      onSubmit={(e) => {
        e.preventDefault();
        onSave();
      }}
      sx={{ mt: 1, p: 1.5, border: `1px solid ${LINE}`, borderRadius: 2, bgcolor: '#f7f9fc' }}
      data-testid="chronology-edit"
    >
      <Typography sx={{ fontSize: 12, fontWeight: 800, color: MUTED, letterSpacing: 0.4, mb: 1 }}>
        {title}
      </Typography>
      {children}
      <Stack direction="row" spacing={1} sx={{ mt: 1.5, alignItems: 'center', flexWrap: 'wrap' }}>
        <Button
          type="submit"
          size="small"
          variant="contained"
          color={saveColor}
          disabled={busy}
          startIcon={busy ? <CircularProgress size={14} color="inherit" /> : undefined}
        >
          {saveLabel}
        </Button>
        <Button size="small" onClick={onCancel} disabled={busy}>
          Annuler
        </Button>
        <Box sx={{ flex: 1 }} />
        {extra}
      </Stack>
    </Box>
  );
}

const dateField = { size: 'small', type: 'date', slotProps: { inputLabel: { shrink: true } } } as const;

function PeriodForm({
  entry,
  edits,
  onDone,
}: {
  entry: BinderChronologyEntry;
  edits: Edits;
  onDone: () => void;
}) {
  const initial = { number: entry.number ?? '', start: entry.start_date ?? '', end: entry.end_date ?? '' };
  const [values, setValues] = useState(initial);
  const save = () => {
    // Seuls les champs modifiés partent : une date de fin effacée redevient calculée.
    const payload: PeriodValues = {};
    if (values.number !== initial.number) payload.number = values.number;
    if (values.start !== initial.start) payload.start_date = values.start || null;
    if (values.end !== initial.end) payload.end_date = values.end || null;
    if (!Object.keys(payload).length) return onDone();
    edits.editPeriod.mutate({ period: periodOf(entry), values: payload }, { onSuccess: onDone });
  };
  return (
    <EditPanel
      title={`CORRIGER ${entry.label.toUpperCase()}`}
      onSave={save}
      onCancel={onDone}
      busy={edits.editPeriod.isPending}
    >
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField
          size="small"
          label="N° d'AMM"
          value={values.number}
          onChange={(e) => setValues({ ...values, number: e.target.value })}
          sx={{ flex: 1 }}
          autoFocus
        />
        <TextField
          {...dateField}
          label="Date de début"
          value={values.start}
          onChange={(e) => setValues({ ...values, start: e.target.value })}
        />
        <TextField
          {...dateField}
          label="Date de fin"
          value={values.end}
          onChange={(e) => setValues({ ...values, end: e.target.value })}
        />
      </Stack>
      <Typography sx={{ fontSize: 12, color: MUTED, mt: 0.75 }}>
        Date de fin vide : elle est recalculée d'après la date de début et la durée de validité du pays.
      </Typography>
    </EditPanel>
  );
}

function PeriodSelect({
  value,
  onChange,
  options,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  label: string;
}) {
  return (
    <TextField
      select
      size="small"
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      sx={{ minWidth: 200 }}
    >
      {options.map((option) => (
        <MenuItem key={option.value} value={option.value}>
          {option.label}
        </MenuItem>
      ))}
    </TextField>
  );
}

function CancelRenewalForm({
  entry,
  options,
  edits,
  onDone,
}: {
  entry: BinderChronologyEntry;
  options: { value: string; label: string }[];
  edits: Edits;
  onDone: () => void;
}) {
  const pieces = (entry.decisions?.length ?? 0) + (entry.others?.length ?? 0);
  const targets = options.filter((option) => option.value !== entry.renewal_id);
  const [moveTo, setMoveTo] = useState<string>(targets[0]?.value ?? 'archive');
  return (
    <EditPanel
      title={`SUPPRIMER ${entry.label.toUpperCase()}`}
      saveLabel="Supprimer la période"
      saveColor="error"
      onSave={() =>
        edits.deletePeriod.mutate(
          { period: entry.renewal_id!, moveTo: pieces && moveTo !== 'archive' ? moveTo : null },
          { onSuccess: onDone },
        )
      }
      onCancel={onDone}
      busy={edits.deletePeriod.isPending}
    >
      <Typography sx={{ fontSize: 13, color: INK }}>
        Pour un renouvellement saisi à tort ou en double (créé par un import). L'échéance et le statut de
        l'AMM sont recalculés.
      </Typography>
      {pieces > 0 && (
        <Box sx={{ mt: 1.25 }}>
          <PeriodSelect
            label={`${pieces} pièce${pieces > 1 ? 's' : ''} à ranger sur`}
            value={moveTo}
            onChange={setMoveTo}
            options={[...targets, { value: 'archive', label: 'Archiver les pièces' }]}
          />
        </Box>
      )}
    </EditPanel>
  );
}

function DocumentForm({
  doc,
  current,
  options,
  edits,
  canRemove,
  onDone,
}: {
  doc: BinderChronologyDocument;
  current: ChronologyPeriod;
  options: { value: string; label: string }[];
  edits: Edits;
  canRemove: boolean;
  onDone: () => void;
}) {
  const [date, setDate] = useState(doc.document_date);
  const [kind, setKind] = useState(doc.kind as BinderDocumentKind);
  const [target, setTarget] = useState<string>(current);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const busy = edits.editDocument.isPending || edits.removeDocument.isPending;
  const save = () => {
    const values = {
      ...(date && date !== doc.document_date ? { document_date: date } : {}),
      ...(kind !== doc.kind ? { kind } : {}),
      ...(target !== current ? { period: target } : {}),
    };
    if (!Object.keys(values).length) return onDone();
    edits.editDocument.mutate({ document: doc.document_id, values }, { onSuccess: onDone });
  };
  return (
    <EditPanel
      title={`CORRIGER LA PIÈCE « ${doc.kind_label.toUpperCase()} DU ${formatDate(doc.document_date)} »`}
      onSave={save}
      onCancel={onDone}
      busy={busy}
      extra={
        canRemove &&
        (confirmRemove ? (
          <Button
            size="small"
            color="error"
            variant="outlined"
            disabled={busy}
            onClick={() => edits.removeDocument.mutate(doc.document_id, { onSuccess: onDone })}
          >
            Confirmer le retrait
          </Button>
        ) : (
          <Button
            size="small"
            color="error"
            startIcon={<DeleteOutlineIcon />}
            disabled={busy}
            onClick={() => setConfirmRemove(true)}
          >
            Retirer la pièce
          </Button>
        ))
      }
    >
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ flexWrap: 'wrap' }}>
        <TextField
          {...dateField}
          label="Date du document"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <TextField
          select
          size="small"
          label="Type"
          value={kind}
          onChange={(e) => setKind(e.target.value as BinderDocumentKind)}
          sx={{ minWidth: 170 }}
        >
          {DOCUMENT_KINDS.map((option) => (
            <MenuItem key={option.value} value={option.value}>
              {option.label}
            </MenuItem>
          ))}
        </TextField>
        <PeriodSelect label="Période" value={target} onChange={setTarget} options={options} />
      </Stack>
      {confirmRemove && (
        <Typography sx={{ fontSize: 12, color: '#c62828', mt: 0.75 }}>
          La pièce quitte la page ; elle reste dans l'historique des documents archivés.
        </Typography>
      )}
    </EditPanel>
  );
}

function AddDocumentForm({
  entry,
  edits,
  onDone,
}: {
  entry: BinderChronologyEntry;
  edits: Edits;
  onDone: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<BinderDocumentKind>(entry.kind === 'pending' ? 'RECEPISSE' : 'AMM');
  const [date, setDate] = useState((entry.kind === 'pending' ? entry.filing_date : entry.start_date) ?? '');
  const [missing, setMissing] = useState(false);
  const save = () => {
    if (!file || !date) return setMissing(true);
    edits.addDocument.mutate(
      { file, kind, document_date: date, period: periodOf(entry) },
      { onSuccess: onDone },
    );
  };
  return (
    <EditPanel
      title={`AJOUTER UNE PIÈCE — ${entry.label.toUpperCase()}`}
      onSave={save}
      onCancel={onDone}
      busy={edits.addDocument.isPending}
    >
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1}
        sx={{ alignItems: { sm: 'center' }, flexWrap: 'wrap' }}
      >
        <input
          ref={input}
          type="file"
          accept={SCAN_ACCEPT}
          hidden
          data-testid="chronology-file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <Button size="small" variant="outlined" onClick={() => input.current?.click()} sx={{ maxWidth: 260 }}>
          <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {file ? file.name : 'Choisir le scan (PDF, JPEG, PNG)'}
          </Box>
        </Button>
        <TextField
          select
          size="small"
          label="Type"
          value={kind}
          onChange={(e) => setKind(e.target.value as BinderDocumentKind)}
          sx={{ minWidth: 170 }}
        >
          {DOCUMENT_KINDS.map((option) => (
            <MenuItem key={option.value} value={option.value}>
              {option.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          {...dateField}
          label="Date du document"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </Stack>
      <Typography sx={{ fontSize: 12, color: missing ? '#c62828' : MUTED, mt: 0.75 }}>
        {missing
          ? 'Choisissez le scan et indiquez sa date.'
          : 'Rangée telle quelle sur cette période, à la date saisie (pas de lecture automatique).'}
      </Typography>
    </EditPanel>
  );
}

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
}: {
  page: BinderPage;
  binderKey: string;
  open: boolean;
  onClose: () => void;
  scanImport: ScanImport;
}) {
  const [viewed, setViewed] = useState<BinderChronologyDocument | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const edits = useChronologyEdits(binderKey, page.amm_id);
  const user = useCurrentUser();
  const canRemove = user?.role === 'CEO_ADMIN';
  const issues = chronologyIssues(page);
  const periods = page.chronology.filter((entry) => entry.kind !== 'gap');
  const options = periods.map((entry) => ({ value: periodOf(entry), label: entry.label }));
  // Seul le renouvellement le plus récent se supprime : on défait la dernière étape.
  const latest = periods
    .filter((entry) => entry.renewal_id)
    .reduce<BinderChronologyEntry | null>(
      (best, entry) => (!best || (entry.sequence ?? 0) > (best.sequence ?? 0) ? entry : best),
      null,
    );
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
            const color = KIND_COLORS[entry.kind];
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
                        {latest && entry.renewal_id === latest.renewal_id && (
                          <Tooltip title="Supprimer ce renouvellement (saisi à tort ou en double)">
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
                  {openHere?.type === 'period' && <PeriodForm entry={entry} edits={edits} onDone={done} />}
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
                      canRemove={canRemove}
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
