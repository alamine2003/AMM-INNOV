import { FitToPage } from './FitToPage';
import { extractErrorMessage } from '@/api/client';
import { useCheckPage, useMarkPrint, useUncheckPage } from '@/api/hooks/useBinders';
import { useValidityYears } from '@/api/hooks/useCatalog';
import type {
  BinderCorrection,
  BinderDetail,
  BinderField,
  BinderPage,
  BinderResult,
  BinderSectionSummary,
  BinderSlot,
} from '@/api/types';
import { useCan } from '@/features/auth/authStore';
import PrintIcon from '@mui/icons-material/Print';
import { formatDate, formatDateTime } from '@/lib/dates';
import AddIcon from '@mui/icons-material/Add';
import CheckIcon from '@mui/icons-material/Check';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import EditIcon from '@mui/icons-material/Edit';
import FolderOffIcon from '@mui/icons-material/FolderOff';
import UndoIcon from '@mui/icons-material/Undo';
import { Alert, Box, Button, Stack, TextField, Tooltip, Typography } from '@mui/material';
import { useState } from 'react';
import { ChronologyDialog } from './ChronologyDialog';
import { chronologyIssues } from './chronologyShared';
import { ConformityPanel } from './ConformityPanel';
import { DeletePageDialog, RenamePageDialog } from './PageManage';
import { ScanImportButton, ScanImportStatus, usePageScanImport } from './PageScanImport';
import { Holes, INK, LINE, MUTED, Pill, STATUS_COLORS, Stamp, paperSx } from './paper';
import { ScanThumbnail } from './ScanThumbnail';
import { FoldedCorner, PageTrace, Sleeve } from './SheetDecor';
import { FIELDS, SLOTS, type Values, initialValues, show } from './sheetFields';
import { SlotCard, agedSx } from './SlotCard';
/** Une page d'AMM du classeur, avec le constat de l'archiviste. */
export function BinderSheet({
  binder,
  page,
  section,
  total,
  onChecked,
}: {
  binder: BinderDetail;
  page: BinderPage;
  section: BinderSectionSummary;
  total: number;
  onChecked: (result: BinderResult) => void;
}) {
  const years = useValidityYears(binder.country_iso2);
  const check = useCheckPage(binder.key);
  const uncheck = useUncheckPage(binder.key);
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState<Values>(() => initialValues(page));
  const [note, setNote] = useState(page.check?.note ?? '');
  const [justStamped, setJustStamped] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const scanImport = usePageScanImport(binder.key, page.amm_id);
  const [chronologyOpen, setChronologyOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // Pas de renouvellement : le bloc n'apparaît pas (rien à remplir de force) ; en correction, il
  // s'ouvre seulement si le papier porte un renouvellement que la fiche n'a pas.
  const [addingRenewal, setAddingRenewal] = useState(false);
  // Renommer ou supprimer une page touche toute l'application : droits donnés par le backend.
  // Lecture seule hors CEO et siège : ni constat, ni correction, ni scan, ni marque.
  const canEdit = useCan('binder.edit');
  const markPrint = useMarkPrint(binder.key);
  const canRename = useCan('binder.rename_page');
  const canDelete = useCan('binder.delete_page');
  const missing = chronologyIssues(page);
  const busy = check.isPending || uncheck.isPending || markPrint.isPending;

  // Le formulaire repart des valeurs actuelles de la page : un scan rangé ou une correction de
  // la chronologie a pu les changer depuis l'ouverture, et renvoyer les anciennes les écraserait.
  const startEditing = () => {
    setValues(initialValues(page));
    setAddingRenewal(false);
    setEditing(true);
  };

  const cancelEditing = () => {
    setEditing(false);
    setValues(initialValues(page));
    setError(null);
  };

  const send = (result: BinderResult, corrections: BinderCorrection[] = []) => {
    setError(null);
    check.mutate(
      { amm: page.amm_id, result, corrections, note },
      {
        onSuccess: () => {
          setEditing(false);
          setJustStamped(true);
          onChecked(result);
        },
        onError: (e) => setError(extractErrorMessage(e)),
      },
    );
  };

  const submitCorrection = () => {
    const initial = initialValues(page);
    const corrections: BinderCorrection[] = Object.keys(values)
      .filter((key) => values[key] !== initial[key])
      .map((key) => {
        const [slot, field] = key.split('.') as [BinderSlot, BinderField];
        return { slot, field, value: values[key] || null };
      });
    if (!corrections.length && !note.trim()) {
      setError('Aucune valeur modifiée : utilisez « Papier conforme » si la page est juste.');
      return;
    }
    send('CORRIGE', corrections);
  };

  const scan = page.scan;
  const currentScan = !!scan && scan.is_current !== false;
  const stamp = page.check;
  // Le dashboard ou un import a changé la fiche depuis le constat : le tampon ne vaut plus.
  const stale = page.changed_since_check.length > 0;
  // Dossier complet : rangé dans sa pochette plastique. AMM expirée : papier jauni, coin corné.
  const sleeved = page.dossier_state === 'COMPLET';
  const aged = page.status === 'EXPIRE';
  return (
    <Box
      sx={aged ? { ...(paperSx as object), ...agedSx } : paperSx}
      data-testid="binder-sheet"
      onDragOver={(e) => {
        if (!canEdit || !Array.from(e.dataTransfer.types).includes('Files')) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (canEdit) scanImport.start(Array.from(e.dataTransfer.files));
      }}
    >
      <Holes />
      {sleeved && <Sleeve />}
      {aged && <FoldedCorner />}
      {dragging && (
        <Box
          sx={{
            position: 'absolute',
            inset: 12,
            zIndex: 3,
            border: '3px dashed #204093',
            borderRadius: 3,
            bgcolor: 'rgba(32,64,147,0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            pointerEvents: 'none',
            textAlign: 'center',
            p: 3,
          }}
        >
          <Typography sx={{ fontWeight: 800, color: '#204093', fontSize: 18 }}>
            Déposez le scan de la décision : il sera lu et rangé sur {page.product_name}
          </Typography>
        </Box>
      )}
      <FitToPage sx={{ pl: { xs: 6, sm: 7 }, pr: { xs: 2, sm: 4 }, py: 2.5 }}>
        <Stack
          direction="row"
          justifyContent="space-between"
          sx={{ color: MUTED, fontSize: 11, fontWeight: 700 }}
        >
          <span>
            {binder.country_name.toUpperCase()} · CLASSEUR {binder.title.toUpperCase()}
          </span>
          <span>
            PAGE {page.page} / {total}
          </span>
        </Stack>
        <Typography
          component="h2"
          sx={{ fontSize: { xs: 20, sm: 24 }, fontWeight: 900, color: INK, mt: 1, lineHeight: 1.15 }}
        >
          {page.product_name}
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.75, mb: 1.5, flexWrap: 'wrap' }}>
          <Pill color={section.color}>{section.label}</Pill>
          <Typography sx={{ fontSize: 12, color: MUTED }}>
            page {page.section_page} / {section.total} de la gamme
          </Typography>
          {(canRename || canDelete) && (
            <Stack direction="row" spacing={0.5} sx={{ ml: 'auto !important' }}>
              {canRename && (
                <Button
                  size="small"
                  startIcon={<EditIcon fontSize="small" />}
                  onClick={() => setRenaming(true)}
                  sx={{ color: MUTED, fontSize: 12 }}
                  data-testid="rename-page"
                >
                  Titre
                </Button>
              )}
              {canDelete && (
                <Button
                  size="small"
                  color="error"
                  startIcon={<DeleteOutlineIcon fontSize="small" />}
                  onClick={() => setDeleting(true)}
                  sx={{ fontSize: 12 }}
                  data-testid="delete-page"
                >
                  Supprimer la page
                </Button>
              )}
            </Stack>
          )}
        </Stack>
        {renaming && <RenamePageDialog binder={binder} page={page} open onClose={() => setRenaming(false)} />}
        {deleting && <DeletePageDialog binder={binder} page={page} open onClose={() => setDeleting(false)} />}

        <Stack direction="row" gap={1.5} flexWrap="wrap">
          {SLOTS.filter(({ slot }) => slot === 'original' || page.renewal || (editing && addingRenewal)).map(
            ({ slot, title }) => (
              <SlotCard
                key={slot}
                page={page}
                slot={slot}
                title={title}
                editing={editing}
                years={years}
                values={values}
                onChange={(key, value) => setValues((v) => ({ ...v, [key]: value }))}
                canEdit={canEdit}
                busy={busy}
                onStartEdit={startEditing}
                onSave={submitCorrection}
                onCancel={cancelEditing}
              />
            ),
          )}
          {editing && !page.renewal && !addingRenewal && (
            <Button
              size="small"
              startIcon={<AddIcon />}
              onClick={() => setAddingRenewal(true)}
              sx={{ alignSelf: 'center' }}
              data-testid="add-renewal-slot"
            >
              Le papier porte un renouvellement
            </Button>
          )}
        </Stack>

        <Stack
          direction="row"
          gap={2}
          alignItems="center"
          sx={{ mt: 1.5, bgcolor: '#fff', border: `1px solid ${LINE}`, borderRadius: 2, p: 1.75 }}
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontSize: 11, fontWeight: 800, color: MUTED, letterSpacing: 0.6, mb: 1 }}>
              SITUATION
            </Typography>
            <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
              <Pill color={STATUS_COLORS[page.status] ?? MUTED}>{page.status_label}</Pill>
              <Typography sx={{ fontSize: 13 }}>
                {page.dossier_state === 'COMPLET' ? 'Dossier complet' : 'Dossier incomplet'}
              </Typography>
              {page.to_scan && <Pill color="#c62828">À SCANNER</Pill>}
              {page.to_print && <Pill color="#1565c0">À IMPRIMER</Pill>}
              {page.pending_renewal && (
                <Box
                  aria-label="Renouvellement déposé"
                  sx={{
                    display: 'inline-flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    px: 1,
                    border: '2px solid #1565c0',
                    borderRadius: 1,
                    color: '#1565c0',
                    transform: 'rotate(-6deg)',
                    mixBlendMode: 'multiply',
                    lineHeight: 1.1,
                  }}
                >
                  <Box component="span" sx={{ fontWeight: 900, fontSize: 15, letterSpacing: 1 }}>
                    {page.pending_renewal.workflow_status === 'DEPOSE' ? 'DÉPOSÉ' : 'EN INSTRUCTION'}
                  </Box>
                  {page.pending_renewal.filing_date && (
                    <Box component="span" sx={{ fontSize: 10, fontWeight: 700 }}>
                      le {formatDate(page.pending_renewal.filing_date)}
                    </Box>
                  )}
                </Box>
              )}
            </Stack>
            <Typography
              sx={{
                fontSize: 13,
                mt: 1,
                color: currentScan ? INK : '#c62828',
                fontWeight: currentScan ? 400 : 700,
              }}
            >
              {!scan
                ? 'Aucun scan dans AMM GH'
                : currentScan
                  ? `Décision scannée du ${formatDate(scan.document_date)}${scan.page_count ? ` · ${scan.page_count} p.` : ''}`
                  : `Décision en vigueur non scannée (dernier scan : décision du ${formatDate(scan.document_date)})`}
            </Typography>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              {canEdit && <ScanImportButton scanImport={scanImport} hasScan={currentScan} />}
              {canEdit && scan && (
                <Tooltip
                  describeChild
                  title={
                    page.to_print
                      ? 'La feuille est imprimée et rangée dans le classeur'
                      : 'Le scan existe mais sa feuille manque dans le classeur papier (compté dans le bilan)'
                  }
                >
                  <Button
                    size="small"
                    color={page.to_print ? 'success' : 'primary'}
                    startIcon={page.to_print ? <CheckIcon /> : <PrintIcon />}
                    disabled={busy}
                    onClick={() => markPrint.mutate({ amm: page.amm_id, toPrint: !page.to_print })}
                    data-testid="mark-print"
                  >
                    {page.to_print ? 'Imprimée et rangée' : 'À imprimer'}
                  </Button>
                </Tooltip>
              )}
              <Button
                size="small"
                color={missing ? 'warning' : 'primary'}
                onClick={() => setChronologyOpen(true)}
                sx={{ mt: 1 }}
                data-testid="open-chronology"
              >
                Chronologie
                {missing ? ` · ${missing} manque${missing > 1 ? 's' : ''}` : ''}
              </Button>
            </Stack>
          </Box>
          {scan && (
            <ScanThumbnail
              documentId={scan.document_id}
              documentDate={scan.document_date}
              title={`${page.product_name} — décision du ${formatDate(scan.document_date)}`}
              width={96}
              stack={Math.max(page.decision_count - 1, 0)}
              onOpen={() => setChronologyOpen(true)}
              label={`Chronologie des ${page.decision_count} décisions de ${page.product_name}`}
            />
          )}
          <ChronologyDialog
            page={page}
            binderKey={binder.key}
            years={years}
            open={chronologyOpen}
            onClose={() => setChronologyOpen(false)}
            scanImport={scanImport}
          />
        </Stack>

        <ScanImportStatus scanImport={scanImport} />

        <ConformityPanel page={page} />

        {stale && !editing && (
          <Alert severity="warning" sx={{ mt: 1.5, bgcolor: '#fff3e0' }} data-testid="page-stale">
            <Typography variant="subtitle2">
              À revérifier : la fiche a changé depuis le constat ({page.changed_by}).
            </Typography>
            {page.changed_since_check.map((change) => (
              <Box key={`${change.slot}.${change.field}`} sx={{ fontSize: 13 }}>
                {FIELDS.find((f) => f.field === change.field)?.label} (
                {change.slot === 'original' ? 'origine' : 'renouvellement'}) : vérifié{' '}
                <b>{show(change.field, change.checked)}</b>, maintenant{' '}
                <b>{show(change.field, change.now)}</b>
              </Box>
            ))}
          </Alert>
        )}
        <PageTrace page={page} />

        {page.discrepancies.length > 0 && !editing && (
          <Alert severity="warning" sx={{ mt: 1.5, py: 0.25, bgcolor: '#fff8e1' }}>
            Écart entre la fiche et le scan : vérifiez sur le papier, puis « Papier conforme » si la fiche est
            juste ou « Corriger ».
          </Alert>
        )}

        {editing && (
          <TextField
            size="small"
            fullWidth
            label="Note (facultatif)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            sx={{ mt: 1.5, bgcolor: '#fff' }}
          />
        )}
        {error && (
          <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <Stack direction="column" gap={1.5} sx={{ mt: 2.5, pb: 1 }}>
          {!canEdit ? null : editing ? (
            <Stack direction="row" gap={1}>
              <Button variant="contained" color="warning" onClick={submitCorrection} disabled={busy}>
                Valider la correction
              </Button>
              <Button onClick={cancelEditing} disabled={busy}>
                Annuler
              </Button>
            </Stack>
          ) : (
            <Stack direction="row" gap={1} flexWrap="wrap">
              <Tooltip
                describeChild
                title="Le dossier papier est dans le classeur, la date et le n° d'AMM sont justes (touche C)"
              >
                <Button
                  variant="contained"
                  color="success"
                  startIcon={<CheckIcon />}
                  onClick={() => send('CONFORME')}
                  disabled={busy}
                  data-action="conforme"
                >
                  Papier conforme
                </Button>
              </Tooltip>
              <Tooltip describeChild title="Saisir la valeur lue sur le papier (touche E)">
                <Button
                  variant="outlined"
                  color="warning"
                  startIcon={<EditIcon />}
                  onClick={startEditing}
                  disabled={busy}
                  data-action="corriger"
                >
                  Corriger
                </Button>
              </Tooltip>
              <Tooltip describeChild title="Pas de dossier papier à cet endroit (touche A)">
                <Button
                  variant="outlined"
                  color="error"
                  startIcon={<FolderOffIcon />}
                  onClick={() => send('ABSENT')}
                  disabled={busy}
                  data-action="absent"
                >
                  Absent du classeur
                </Button>
              </Tooltip>
            </Stack>
          )}
          {stamp && !editing && (
            <Stack direction="row" justifyContent="space-between" alignItems="flex-end" gap={2}>
              {stamp.note ? (
                <Box
                  aria-label="Note de l'archiviste"
                  sx={{
                    position: 'relative',
                    flexShrink: 0,
                    width: 170,
                    mt: 1,
                    p: 1.25,
                    bgcolor: '#fff59d',
                    color: '#4a3b00',
                    fontSize: 12,
                    lineHeight: 1.35,
                    transform: 'rotate(-3deg)',
                    boxShadow: '2px 4px 8px rgba(0,0,0,0.18)',
                    '&::before': {
                      content: '""',
                      position: 'absolute',
                      top: -7,
                      left: '50%',
                      width: 46,
                      height: 14,
                      ml: '-23px',
                      bgcolor: 'rgba(255,255,255,0.55)',
                      transform: 'rotate(-4deg)',
                    },
                  }}
                >
                  {stamp.note}
                  <Box sx={{ mt: 0.5, fontSize: 10, opacity: 0.7 }}>— {stamp.checked_by}</Box>
                </Box>
              ) : (
                <span />
              )}
              <Stack alignItems="center" spacing={1} sx={{ pr: { sm: 3 } }}>
                <Box sx={{ opacity: stale ? 0.4 : 1 }}>
                  <Stamp
                    result={stamp.result}
                    caption={`${formatDate(stamp.checked_at)} · ${stamp.checked_by ?? ''}`}
                    animate={justStamped}
                  />
                </Box>
                {canEdit && (
                  <Button
                    size="small"
                    startIcon={<UndoIcon />}
                    onClick={() => uncheck.mutate(page.amm_id, { onSuccess: () => setJustStamped(false) })}
                    disabled={busy}
                    sx={{ color: MUTED }}
                  >
                    Annuler le constat
                  </Button>
                )}
              </Stack>
            </Stack>
          )}
        </Stack>
        {stamp && stamp.corrections.length > 0 && !editing && (
          <Box sx={{ fontSize: 12, color: MUTED }}>
            <b>Corrigé sur le papier</b> ({formatDateTime(stamp.checked_at)}) :{' '}
            {stamp.corrections
              .map(
                (c) =>
                  `${FIELDS.find((f) => f.field === c.field)?.label} (${c.slot === 'original' ? 'origine' : 'renouvellement'}) ${show(c.field, c.old)} → ${show(c.field, c.new)}`,
              )
              .join(' · ')}
          </Box>
        )}
      </FitToPage>
    </Box>
  );
}
