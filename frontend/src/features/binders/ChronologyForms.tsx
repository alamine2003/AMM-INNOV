import { type ChronologyPeriod, type PeriodValues } from '@/api/hooks/useBinders';
import type { BinderChronologyDocument, BinderChronologyEntry, BinderDocumentKind } from '@/api/types';
import { DateInput, ValidityLine } from '@/components/DateInput';
import { addValidity, formatDate } from '@/lib/dates';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { Box, Button, CircularProgress, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { DOCUMENT_KINDS, type Edits, periodOf } from './chronologyShared';
import { SCAN_ACCEPT } from './PageScanImport';
import { INK, LINE, MUTED } from './paper';

/** Formulaires de la chronologie : période, suppression d'un passage, pièces. */

/** Petit formulaire posé sous une période, dans le fil de la chronologie. */
export function EditPanel({
  title,
  children,
  onSave,
  onCancel,
  saveLabel,
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
  const { t } = useTranslation();
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
          {saveLabel ?? t('app.save')}
        </Button>
        <Button size="small" onClick={onCancel} disabled={busy}>
          {t('app.cancel')}
        </Button>
        <Box sx={{ flex: 1 }} />
        {extra}
      </Stack>
    </Box>
  );
}

export function PeriodForm({
  entry,
  edits,
  years,
  onDone,
}: {
  entry: BinderChronologyEntry;
  edits: Edits;
  years: number;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const initial = { number: entry.number ?? '', start: entry.start_date ?? '', end: entry.end_date ?? '' };
  const [values, setValues] = useState(initial);
  // Début corrigé : la fin suit (début + durée du pays) tant qu'on ne la retouche pas.
  const [endFollows, setEndFollows] = useState(false);
  const save = () => {
    // Seuls les champs modifiés partent : une fin qui suit le début est recalculée par le serveur.
    const payload: PeriodValues = {};
    if (values.number !== initial.number) payload.number = values.number;
    if (values.start !== initial.start) payload.start_date = values.start || null;
    if (!endFollows && values.end !== initial.end) payload.end_date = values.end || null;
    if (!Object.keys(payload).length) return onDone();
    edits.editPeriod.mutate({ period: periodOf(entry), values: payload }, { onSuccess: onDone });
  };
  return (
    <EditPanel
      title={t('binders.forms.fixTitle', { label: entry.label.toUpperCase() })}
      onSave={save}
      onCancel={onDone}
      busy={edits.editPeriod.isPending}
    >
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField
          size="small"
          label={t('binders.fields.number')}
          value={values.number}
          onChange={(e) => setValues({ ...values, number: e.target.value })}
          sx={{ flex: 1 }}
          autoFocus
        />
        <DateInput
          size="small"
          fullWidth={false}
          label={t('binders.fields.startDate')}
          value={values.start}
          onChange={(value) => {
            setValues({ ...values, start: value ?? '', end: addValidity(value, years) ?? '' });
            setEndFollows(true);
          }}
        />
        <DateInput
          size="small"
          fullWidth={false}
          label={t('binders.fields.endDate')}
          value={values.end}
          onChange={(value) => {
            setValues({ ...values, end: value ?? '' });
            setEndFollows(false);
          }}
        />
      </Stack>
      <Box sx={{ mt: 0.75 }}>
        <ValidityLine start={values.start || null} end={values.end || null} years={years} auto={endFollows} />
      </Box>
    </EditPanel>
  );
}

export function PeriodSelect({
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

export function CancelRenewalForm({
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
  const { t } = useTranslation();
  const pieces = (entry.decisions?.length ?? 0) + (entry.others?.length ?? 0);
  const targets = options.filter((option) => option.value !== entry.renewal_id);
  const [moveTo, setMoveTo] = useState<string>(
    targets.find((option) => option.value === 'origin')?.value ?? targets[0]?.value ?? 'origin',
  );
  return (
    <EditPanel
      title={t('binders.forms.deleteTitle', { label: entry.label.toUpperCase() })}
      saveLabel={t('binders.forms.deletePassage')}
      saveColor="error"
      onSave={() => edits.deletePeriod.mutate({ period: entry.renewal_id!, moveTo }, { onSuccess: onDone })}
      onCancel={onDone}
      busy={edits.deletePeriod.isPending}
    >
      <Typography sx={{ fontSize: 13, color: INK }}>{t('binders.forms.deleteHelp')}</Typography>
      {pieces > 0 && (
        <Box sx={{ mt: 1.25 }}>
          <PeriodSelect
            label={t('binders.forms.moveTo', { count: pieces })}
            value={moveTo}
            onChange={setMoveTo}
            options={targets}
          />
        </Box>
      )}
    </EditPanel>
  );
}

export function DocumentForm({
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
  const { t } = useTranslation();
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
      title={t('binders.forms.fixDocTitle', {
        kind: doc.kind_label.toUpperCase(),
        date: formatDate(doc.document_date),
      })}
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
            {t('binders.forms.confirmRemove')}
          </Button>
        ) : (
          <Button
            size="small"
            color="error"
            startIcon={<DeleteOutlineIcon />}
            disabled={busy}
            onClick={() => setConfirmRemove(true)}
          >
            {t('binders.forms.removeDoc')}
          </Button>
        ))
      }
    >
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ flexWrap: 'wrap' }}>
        <DateInput
          size="small"
          fullWidth={false}
          label={t('binders.forms.documentDate')}
          value={date}
          onChange={(value) => setDate(value ?? '')}
        />
        <TextField
          select
          size="small"
          label={t('binders.forms.type')}
          value={kind}
          onChange={(e) => setKind(e.target.value as BinderDocumentKind)}
          sx={{ minWidth: 170 }}
        >
          {DOCUMENT_KINDS.map((option) => (
            <MenuItem key={option.value} value={option.value}>
              {t(option.labelKey)}
            </MenuItem>
          ))}
        </TextField>
        <PeriodSelect
          label={t('binders.forms.period')}
          value={target}
          onChange={setTarget}
          options={options}
        />
      </Stack>
      {confirmRemove && (
        <Typography sx={{ fontSize: 12, color: '#c62828', mt: 0.75 }}>
          {t('binders.forms.removeNote')}
        </Typography>
      )}
    </EditPanel>
  );
}

export function AddDocumentForm({
  entry,
  edits,
  onDone,
}: {
  entry: BinderChronologyEntry;
  edits: Edits;
  onDone: () => void;
}) {
  const { t } = useTranslation();
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
      title={t('binders.forms.addTitle', { label: entry.label.toUpperCase() })}
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
            {file ? file.name : t('binders.forms.chooseScan')}
          </Box>
        </Button>
        <TextField
          select
          size="small"
          label={t('binders.forms.type')}
          value={kind}
          onChange={(e) => setKind(e.target.value as BinderDocumentKind)}
          sx={{ minWidth: 170 }}
        >
          {DOCUMENT_KINDS.map((option) => (
            <MenuItem key={option.value} value={option.value}>
              {t(option.labelKey)}
            </MenuItem>
          ))}
        </TextField>
        <DateInput
          size="small"
          fullWidth={false}
          label={t('binders.forms.documentDate')}
          value={date}
          onChange={(value) => setDate(value ?? '')}
        />
      </Stack>
      <Typography sx={{ fontSize: 12, color: missing ? '#c62828' : MUTED, mt: 0.75 }}>
        {missing ? t('binders.forms.missingScan') : t('binders.forms.filedAsIs')}
      </Typography>
    </EditPanel>
  );
}
