import { useState } from 'react';
import { Alert, Box, Button, Stack, TextField, Tooltip, Typography } from '@mui/material';
import CheckIcon from '@mui/icons-material/Check';
import EditIcon from '@mui/icons-material/Edit';
import FolderOffIcon from '@mui/icons-material/FolderOff';
import UndoIcon from '@mui/icons-material/Undo';
import { extractErrorMessage } from '@/api/client';
import { useCheckPage, useUncheckPage } from '@/api/hooks/useBinders';
import type {
  BinderCorrection,
  BinderDetail,
  BinderField,
  BinderPage,
  BinderResult,
  BinderSectionSummary,
  BinderSlot,
} from '@/api/types';
import { formatDate, formatDateTime } from '@/lib/dates';
import { ScanImportButton, ScanImportStatus, usePageScanImport } from './PageScanImport';
import { ScanThumbnail } from './ScanThumbnail';
import { Holes, INK, LINE, MUTED, Pill, STATUS_COLORS, Stamp, paperSx } from './paper';

const FIELDS: { field: BinderField; label: string }[] = [
  { field: 'number', label: "N° d'AMM" },
  { field: 'start_date', label: 'Date de début' },
  { field: 'end_date', label: 'Date de fin' },
];
const SLOTS: { slot: BinderSlot; title: string }[] = [
  { slot: 'original', title: "AMM d'origine" },
  { slot: 'renewal', title: 'Dernier renouvellement' },
];

type Values = Record<string, string>;
const id = (slot: BinderSlot, field: BinderField) => `${slot}.${field}`;

function initialValues(page: BinderPage): Values {
  const values: Values = {};
  for (const { slot } of SLOTS) {
    const source = slot === 'original' ? page.original : page.renewal;
    for (const { field } of FIELDS) values[id(slot, field)] = (source?.[field] as string | null) ?? '';
  }
  return values;
}

function show(field: BinderField, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  return field === 'number' ? String(value) : formatDate(String(value));
}

function SlotCard({
  page,
  slot,
  title,
  editing,
  values,
  onChange,
}: {
  page: BinderPage;
  slot: BinderSlot;
  title: string;
  editing: boolean;
  values: Values;
  onChange: (key: string, value: string) => void;
}) {
  const source = slot === 'original' ? page.original : page.renewal;
  const gaps = new Map(page.discrepancies.filter((d) => d.slot === slot).map((d) => [d.field, d]));
  const initial = initialValues(page);
  return (
    <Box
      sx={{
        flex: '1 1 220px',
        bgcolor: '#fff',
        border: `1px solid ${LINE}`,
        borderRadius: 2,
        p: 1.75,
        minWidth: 0,
      }}
    >
      <Typography sx={{ fontSize: 11, fontWeight: 800, color: MUTED, letterSpacing: 0.6, mb: 1 }}>
        {title.toUpperCase()}
      </Typography>
      {!source && !editing ? (
        <Typography sx={{ fontStyle: 'italic', color: MUTED, fontSize: 14 }}>
          Aucun renouvellement enregistré
        </Typography>
      ) : (
        FIELDS.map(({ field, label }) => {
          const key = id(slot, field);
          const gap = gaps.get(field);
          const changed = values[key] !== initial[key];
          return (
            <Box key={field} sx={{ py: 0.6, borderBottom: `1px dotted ${LINE}` }}>
              {editing ? (
                <Stack direction="row" spacing={1} alignItems="center">
                  <TextField
                    size="small"
                    label={label}
                    type={field === 'number' ? 'text' : 'date'}
                    value={values[key]}
                    onChange={(e) => onChange(key, e.target.value)}
                    slotProps={{ inputLabel: { shrink: true } }}
                    sx={{
                      flex: 1,
                      '& .MuiOutlinedInput-root': { bgcolor: changed ? '#fff3b0' : '#fff' },
                    }}
                  />
                  {gap && (
                    <Tooltip describeChild title="Reprendre la valeur lue sur le scan">
                      <Button size="small" onClick={() => onChange(key, String(gap.scan ?? ''))}>
                        Scan : {show(field, gap.scan)}
                      </Button>
                    </Tooltip>
                  )}
                </Stack>
              ) : (
                <Stack direction="row" alignItems="baseline" spacing={1}>
                  <Typography sx={{ fontSize: 12, color: MUTED, width: 96, flexShrink: 0 }}>
                    {label}
                  </Typography>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography
                      component="span"
                      sx={{
                        fontWeight: 800,
                        fontSize: 15,
                        px: gap ? 0.5 : 0,
                        bgcolor: gap ? '#fff3b0' : 'transparent',
                        wordBreak: 'break-word',
                        whiteSpace: field === 'number' ? 'normal' : 'nowrap',
                      }}
                    >
                      {show(field, source?.[field])}
                    </Typography>
                    {gap && (
                      <Typography sx={{ fontSize: 11, color: '#b45309' }}>
                        le scan indique {show(field, gap.scan)}
                      </Typography>
                    )}
                  </Box>
                </Stack>
              )}
            </Box>
          );
        })
      )}
    </Box>
  );
}

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
  const check = useCheckPage(binder.key);
  const uncheck = useUncheckPage(binder.key);
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState<Values>(() => initialValues(page));
  const [note, setNote] = useState(page.check?.note ?? '');
  const [justStamped, setJustStamped] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const scanImport = usePageScanImport(binder.key, page.amm_id);
  const busy = check.isPending || uncheck.isPending;

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
      setError('Aucune valeur modifiée : utilisez « Conforme » si la page est juste.');
      return;
    }
    send('CORRIGE', corrections);
  };

  const scan = page.scan;
  const stamp = page.check;
  return (
    <Box
      sx={paperSx}
      data-testid="binder-sheet"
      onDragOver={(e) => {
        if (!Array.from(e.dataTransfer.types).includes('Files')) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        scanImport.start(Array.from(e.dataTransfer.files));
      }}
    >
      <Holes />
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
      {stamp?.note && !editing && (
        <Box
          aria-label="Note de l'archiviste"
          sx={{
            position: 'absolute',
            top: 58,
            right: 22,
            zIndex: 2,
            width: 150,
            p: 1.25,
            bgcolor: '#fff59d',
            color: '#4a3b00',
            fontSize: 12,
            lineHeight: 1.35,
            transform: 'rotate(3deg)',
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
      )}
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          pl: { xs: 6, sm: 7 },
          pr: { xs: 2, sm: 4 },
          py: 2.5,
          overflowY: 'auto',
        }}
      >
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
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.75, mb: 1.5 }}>
          <Pill color={section.color}>{section.label}</Pill>
          <Typography sx={{ fontSize: 12, color: MUTED }}>
            page {page.section_page} / {section.total} de la gamme
          </Typography>
        </Stack>

        <Stack direction="row" gap={1.5} flexWrap="wrap">
          {SLOTS.map(({ slot, title }) => (
            <SlotCard
              key={slot}
              page={page}
              slot={slot}
              title={title}
              editing={editing}
              values={values}
              onChange={(key, value) => setValues((v) => ({ ...v, [key]: value }))}
            />
          ))}
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
            </Stack>
            <Typography
              sx={{ fontSize: 13, mt: 1, color: scan ? INK : '#c62828', fontWeight: scan ? 400 : 700 }}
            >
              {scan
                ? `Décision scannée du ${formatDate(scan.document_date)}${scan.page_count ? ` · ${scan.page_count} p.` : ''}`
                : 'Aucun scan dans AMM GH'}
            </Typography>
            <ScanImportButton scanImport={scanImport} hasScan={!!scan} />
          </Box>
          {scan && (
            <ScanThumbnail
              documentId={scan.document_id}
              documentDate={scan.document_date}
              title={`${page.product_name} — décision du ${formatDate(scan.document_date)}`}
              width={96}
            />
          )}
        </Stack>

        <ScanImportStatus scanImport={scanImport} />

        {page.discrepancies.length > 0 && !editing && (
          <Alert severity="warning" sx={{ mt: 1.5, py: 0.25, bgcolor: '#fff8e1' }}>
            Écart entre la fiche et le scan : vérifiez sur le papier, puis « Conforme » si la fiche est juste
            ou « Corriger ».
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
          {editing ? (
            <Stack direction="row" gap={1}>
              <Button variant="contained" color="warning" onClick={submitCorrection} disabled={busy}>
                Valider la correction
              </Button>
              <Button
                onClick={() => {
                  setEditing(false);
                  setValues(initialValues(page));
                  setError(null);
                }}
                disabled={busy}
              >
                Annuler
              </Button>
            </Stack>
          ) : (
            <Stack direction="row" gap={1} flexWrap="wrap">
              <Tooltip describeChild title="Tout est juste sur le papier (touche C)">
                <Button
                  variant="contained"
                  color="success"
                  startIcon={<CheckIcon />}
                  onClick={() => send('CONFORME')}
                  disabled={busy}
                  data-action="conforme"
                >
                  Conforme
                </Button>
              </Tooltip>
              <Tooltip describeChild title="Saisir la valeur lue sur le papier (touche E)">
                <Button
                  variant="outlined"
                  color="warning"
                  startIcon={<EditIcon />}
                  onClick={() => setEditing(true)}
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
            <Stack alignItems="center" spacing={1} sx={{ alignSelf: 'flex-end', pr: { sm: 3 } }}>
              <Stamp
                result={stamp.result}
                caption={`${formatDate(stamp.checked_at)} · ${stamp.checked_by ?? ''}`}
                animate={justStamped}
              />
              <Button
                size="small"
                startIcon={<UndoIcon />}
                onClick={() => uncheck.mutate(page.amm_id, { onSuccess: () => setJustStamped(false) })}
                disabled={busy}
                sx={{ color: MUTED }}
              >
                Annuler le constat
              </Button>
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
      </Box>
    </Box>
  );
}
