import { useRef, useState, type ReactNode } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import CheckIcon from '@mui/icons-material/Check';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DownloadIcon from '@mui/icons-material/Download';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import SendIcon from '@mui/icons-material/Send';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import { useSnackbar } from 'notistack';
import { extractErrorMessage, fetchBlob } from '@/api/client';
import type { useDepositActions } from '@/api/hooks/useDeposits';
import { depositFiles } from '@/api/hooks/useDeposits';
import type { DepositDetail, DepositEventKind, DepositPiece } from '@/api/types';
import { formatDate, formatDateTime, todayIso } from '@/lib/dates';
import { formatBytes, saveBlob } from '@/lib/download';

export const PIECE_ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.odt,.jpg,.jpeg,.png';
export const SCAN_ACCEPT = '.pdf,.jpg,.jpeg,.png';

type Actions = ReturnType<typeof useDepositActions>;

export function useFail() {
  const { enqueueSnackbar } = useSnackbar();
  return (error: unknown) => enqueueSnackbar(extractErrorMessage(error), { variant: 'error' });
}

/** Une étape de la procédure : numéro, titre, état (fait, en cours, à venir). */
export function Section({
  index,
  title,
  subtitle,
  state,
  children,
  testId,
}: {
  index: number;
  title: string;
  subtitle?: ReactNode;
  state: 'done' | 'active' | 'todo';
  children?: ReactNode;
  testId?: string;
}) {
  const color = state === 'done' ? 'success.main' : state === 'active' ? 'primary.main' : 'grey.400';
  return (
    <Card
      variant="outlined"
      sx={{ mb: 2, borderLeft: 4, borderLeftColor: color, opacity: state === 'todo' ? 0.75 : 1 }}
      data-testid={testId}
    >
      <CardContent>
        <Stack direction="row" alignItems="center" gap={1.5} sx={{ mb: children ? 1.5 : 0 }}>
          <Avatar sx={{ bgcolor: color, width: 30, height: 30, fontSize: 15 }}>
            {state === 'done' ? <CheckIcon fontSize="small" /> : index}
          </Avatar>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="subtitle1" fontWeight={700} component="h2">
              {title}
            </Typography>
            {subtitle && (
              <Typography variant="body2" color="text.secondary" component="div">
                {subtitle}
              </Typography>
            )}
          </Box>
          {state === 'todo' && <LockOutlinedIcon fontSize="small" color="disabled" />}
        </Stack>
        {children}
      </CardContent>
    </Card>
  );
}

function FileButton({
  label,
  accept,
  onFile,
  disabled,
  icon = <UploadFileIcon />,
  variant = 'outlined',
}: {
  label: string;
  accept: string;
  onFile: (file: File) => void;
  disabled?: boolean;
  icon?: ReactNode;
  variant?: 'outlined' | 'text' | 'contained';
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <Button
        size="small"
        variant={variant}
        startIcon={icon}
        disabled={disabled}
        onClick={() => input.current?.click()}
      >
        {label}
      </Button>
      <input
        ref={input}
        type="file"
        hidden
        accept={accept}
        aria-label={label}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = '';
        }}
      />
    </>
  );
}

function PieceChip({
  dossierId,
  piece,
  onDelete,
}: {
  dossierId: string;
  piece: DepositPiece;
  onDelete?: () => void;
}) {
  const fail = useFail();
  return (
    <Chip
      size="small"
      variant="outlined"
      icon={<AttachFileIcon />}
      label={`${piece.filename} · ${formatBytes(piece.size_bytes)}`}
      onClick={() =>
        depositFiles
          .piece(dossierId, piece.id)
          .then((blob) => saveBlob(blob, piece.filename))
          .catch(fail)
      }
      onDelete={onDelete}
      deleteIcon={onDelete ? <DeleteOutlineIcon aria-label={`Retirer ${piece.filename}`} /> : undefined}
      sx={{ maxWidth: '100%' }}
    />
  );
}

// --- 1. Pièces -----------------------------------------------------------------------------

export function PiecesSection({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const editable = dossier.can.manage;
  const removable = editable && !dossier.sent_at;
  const [otherLabel, setOtherLabel] = useState('');
  const done = dossier.pieces_done >= dossier.pieces_required;
  return (
    <Section
      index={1}
      title="Montage du dossier"
      subtitle={`${dossier.pieces_done}/${dossier.pieces_required} pièces obligatoires${
        dossier.sent_at ? ' · dossier envoyé : un ajout part au pays en complément' : ''
      }`}
      state={done || dossier.sent_at ? 'done' : 'active'}
      testId="section-pieces"
    >
      <Stack divider={<Box sx={{ borderBottom: 1, borderColor: 'divider' }} />}>
        {dossier.checklist.map(({ piece_type: type, files, done: present }) => (
          <Stack
            key={type.id}
            direction={{ xs: 'column', sm: 'row' }}
            gap={1}
            alignItems={{ sm: 'center' }}
            sx={{ py: 1 }}
            data-testid={`piece-${type.label}`}
          >
            <Stack direction="row" gap={1} alignItems="center" sx={{ flex: '0 0 42%' }}>
              {present ? (
                <CheckCircleIcon color="success" fontSize="small" />
              ) : (
                <RadioButtonUncheckedIcon color={type.required ? 'warning' : 'disabled'} fontSize="small" />
              )}
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  {type.label}
                  {!type.required && (
                    <Typography component="span" variant="caption" color="text.secondary">
                      {' '}
                      (facultative)
                    </Typography>
                  )}
                  {type.country && <Chip size="small" label={type.country} sx={{ ml: 1, height: 18 }} />}
                </Typography>
                {type.help_text && (
                  <Typography variant="caption" color="text.secondary">
                    {type.help_text}
                  </Typography>
                )}
              </Box>
            </Stack>
            <Stack direction="row" gap={0.75} flexWrap="wrap" sx={{ flexGrow: 1, minWidth: 0 }}>
              {files.map((piece) => (
                <PieceChip
                  key={piece.id}
                  dossierId={dossier.id}
                  piece={piece}
                  onDelete={
                    removable ? () => actions.removePiece.mutate(piece.id, { onError: fail }) : undefined
                  }
                />
              ))}
            </Stack>
            {editable && (
              <FileButton
                label={files.length ? 'Ajouter' : 'Joindre'}
                accept={PIECE_ACCEPT}
                disabled={actions.addPiece.isPending}
                onFile={(file) => actions.addPiece.mutate({ file, piece_type: type.id }, { onError: fail })}
              />
            )}
          </Stack>
        ))}
      </Stack>
      {(dossier.other_pieces.length > 0 || editable) && (
        <Box sx={{ mt: 1.5 }}>
          <Typography variant="body2" fontWeight={600} gutterBottom>
            Autres pièces
          </Typography>
          <Stack direction="row" gap={0.75} flexWrap="wrap" sx={{ mb: 1 }}>
            {dossier.other_pieces.map((piece) => (
              <Tooltip key={piece.id} title={piece.label}>
                <span>
                  <PieceChip
                    dossierId={dossier.id}
                    piece={piece}
                    onDelete={
                      removable ? () => actions.removePiece.mutate(piece.id, { onError: fail }) : undefined
                    }
                  />
                </span>
              </Tooltip>
            ))}
          </Stack>
          {editable && (
            <Stack direction="row" gap={1} alignItems="center">
              <TextField
                size="small"
                label="Nom de la pièce"
                placeholder="Procuration, bon de commande…"
                value={otherLabel}
                onChange={(e) => setOtherLabel(e.target.value)}
              />
              <FileButton
                label="Joindre"
                accept={PIECE_ACCEPT}
                disabled={!otherLabel.trim() || actions.addPiece.isPending}
                onFile={(file) =>
                  actions.addPiece.mutate(
                    { file, label: otherLabel.trim() },
                    { onSuccess: () => setOtherLabel(''), onError: fail },
                  )
                }
              />
            </Stack>
          )}
        </Box>
      )}
    </Section>
  );
}

// --- 2. Échantillons -----------------------------------------------------------------------

export function SamplesSection({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const editable = dossier.can.manage && !dossier.sent_at;
  const empty = { batch_number: '', manufactured_on: '', expires_on: '', quantity: '' };
  const [form, setForm] = useState(empty);
  const ok = !dossier.samples_required || dossier.samples.length > 0;
  const valid = form.batch_number.trim() && form.manufactured_on && form.expires_on;
  return (
    <Section
      index={2}
      title="Échantillons"
      subtitle={
        dossier.samples_required
          ? 'Récupérés sur place : n° de lot, date de fabrication, date de péremption.'
          : 'Pas d’échantillons pour ce dépôt.'
      }
      state={ok || dossier.sent_at ? 'done' : 'active'}
      testId="section-samples"
    >
      {dossier.samples.length > 0 && (
        <Table size="small" sx={{ mb: 1 }}>
          <TableHead>
            <TableRow>
              <TableCell>N° de lot</TableCell>
              <TableCell>Fabrication</TableCell>
              <TableCell>Péremption</TableCell>
              <TableCell>Quantité</TableCell>
              {editable && <TableCell />}
            </TableRow>
          </TableHead>
          <TableBody>
            {dossier.samples.map((sample) => (
              <TableRow key={sample.id}>
                <TableCell sx={{ fontWeight: 600 }}>{sample.batch_number}</TableCell>
                <TableCell>{formatDate(sample.manufactured_on)}</TableCell>
                <TableCell>{formatDate(sample.expires_on)}</TableCell>
                <TableCell>{sample.quantity ?? '—'}</TableCell>
                {editable && (
                  <TableCell align="right">
                    <IconButton
                      size="small"
                      aria-label={`Retirer le lot ${sample.batch_number}`}
                      onClick={() => actions.removeSample.mutate(sample.id, { onError: fail })}
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {editable && dossier.samples_required && (
        <Stack direction={{ xs: 'column', md: 'row' }} gap={1} alignItems={{ md: 'center' }}>
          <TextField
            size="small"
            label="N° de lot"
            value={form.batch_number}
            onChange={(e) => setForm({ ...form, batch_number: e.target.value })}
          />
          <TextField
            size="small"
            type="date"
            label="Date de fabrication"
            value={form.manufactured_on}
            onChange={(e) => setForm({ ...form, manufactured_on: e.target.value })}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            size="small"
            type="date"
            label="Date de péremption"
            value={form.expires_on}
            onChange={(e) => setForm({ ...form, expires_on: e.target.value })}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            size="small"
            type="number"
            label="Quantité"
            value={form.quantity}
            onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            sx={{ width: 110 }}
          />
          <Button
            variant="outlined"
            disabled={!valid || actions.addSample.isPending}
            onClick={() =>
              actions.addSample.mutate(
                {
                  batch_number: form.batch_number.trim(),
                  manufactured_on: form.manufactured_on,
                  expires_on: form.expires_on,
                  quantity: form.quantity ? Number(form.quantity) : null,
                },
                { onSuccess: () => setForm(empty), onError: fail },
              )
            }
          >
            Noter le lot
          </Button>
        </Stack>
      )}
      {editable && (
        <FormControlLabel
          sx={{ mt: 1 }}
          control={
            <Switch
              size="small"
              checked={!dossier.samples_required}
              onChange={(e) => actions.samplesRequired.mutate(!e.target.checked, { onError: fail })}
            />
          }
          label="Pas d’échantillons pour ce dépôt"
        />
      )}
    </Section>
  );
}

// --- 3. Envoi au pays ----------------------------------------------------------------------

export function SendSection({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const [note, setNote] = useState('');
  const [downloading, setDownloading] = useState(false);
  const download = () => {
    setDownloading(true);
    depositFiles
      .archive(dossier.id)
      .then((blob) => saveBlob(blob, `Depot_${dossier.amm.country_iso2}_${dossier.amm.product_name}.zip`))
      .catch(fail)
      .finally(() => setDownloading(false));
  };
  const zipButton = (label: string, variant: 'contained' | 'outlined' = 'contained') => (
    <Button variant={variant} startIcon={<DownloadIcon />} onClick={download} disabled={downloading}>
      {downloading ? 'Préparation du dossier…' : label}
    </Button>
  );
  const countryDownloads = dossier.downloads;
  return (
    <Section
      index={3}
      title="Envoi au pays"
      subtitle={
        dossier.sent_at
          ? `Envoyé le ${formatDateTime(dossier.sent_at)}${dossier.sent_by ? ` par ${dossier.sent_by}` : ''}`
          : 'Le pays est prévenu et télécharge le dossier complet (pièces rangées et bordereau).'
      }
      state={dossier.sent_at ? 'done' : dossier.can.manage ? 'active' : 'todo'}
      testId="section-send"
    >
      {!dossier.sent_at && dossier.can.manage && (
        <Stack gap={1.5}>
          {dossier.missing.length > 0 ? (
            <Alert severity="warning">
              <strong>Avant l’envoi :</strong> {dossier.missing.join(' ; ')}.
            </Alert>
          ) : (
            <Alert severity="success">Dossier complet : prêt à partir au pays.</Alert>
          )}
          <TextField
            label="Message au pays (facultatif)"
            placeholder="Échantillons expédiés par DHL, n° de suivi…"
            multiline
            minRows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <Stack direction="row" gap={1}>
            <Button
              variant="contained"
              startIcon={<SendIcon />}
              disabled={dossier.missing.length > 0 || actions.send.isPending}
              onClick={() => actions.send.mutate(note, { onSuccess: () => setNote(''), onError: fail })}
            >
              Envoyer au pays
            </Button>
            {zipButton('Aperçu du dossier (ZIP)', 'outlined')}
          </Stack>
        </Stack>
      )}
      {dossier.sent_at && (
        <Stack gap={1}>
          {dossier.send_note && (
            <Alert severity="info" icon={false}>
              <strong>Message du siège :</strong> {dossier.send_note}
            </Alert>
          )}
          <Box>{zipButton('Télécharger le dossier (ZIP)')}</Box>
          <Typography variant="body2" color="text.secondary" data-testid="downloads">
            {countryDownloads.length
              ? `Téléchargé ${countryDownloads.length} fois — dernier : ${countryDownloads[0].user ?? '?'} le ${formatDateTime(countryDownloads[0].at)}`
              : 'Pas encore téléchargé.'}
          </Typography>
        </Stack>
      )}
    </Section>
  );
}

// --- 4. Dépôt à l'agence -------------------------------------------------------------------

export function DepositSection({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const [date, setDate] = useState(todayIso());
  const [file, setFile] = useState<File | null>(null);
  const deposited =
    !!dossier.renewal.filing_date && ['DEPOSE', 'COMMISSION', 'OBTENU', 'REJETE'].includes(dossier.stage);
  const authority = dossier.amm.authority || 'l’agence de régulation';
  const openAttestation = () => {
    if (!dossier.attestation) return;
    const { id, filename } = dossier.attestation;
    fetchBlob(`/documents/${id}/file`)
      .then((blob) => saveBlob(blob, filename))
      .catch(fail);
  };
  return (
    <Section
      index={4}
      title="Dépôt à l’agence"
      subtitle={
        deposited
          ? `Déposé à ${authority} le ${formatDate(dossier.renewal.filing_date)}`
          : `Le pays dépose le dossier à ${authority}, puis envoie l’attestation de dépôt au siège.`
      }
      state={deposited ? 'done' : dossier.sent_at ? 'active' : 'todo'}
      testId="section-deposit"
    >
      {deposited && dossier.attestation && (
        <Button size="small" startIcon={<AttachFileIcon />} onClick={openAttestation}>
          Attestation de dépôt du {formatDate(dossier.attestation.document_date)}
        </Button>
      )}
      {!deposited && dossier.can.deposit && (
        <Stack direction={{ xs: 'column', md: 'row' }} gap={1} alignItems={{ md: 'center' }}>
          <TextField
            size="small"
            type="date"
            label="Date de dépôt"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: todayIso() } }}
          />
          <FileButton
            label={file ? file.name : 'Attestation de dépôt (PDF, photo)'}
            accept={SCAN_ACCEPT}
            icon={<AttachFileIcon />}
            onFile={setFile}
          />
          <Button
            variant="contained"
            startIcon={<SendIcon />}
            disabled={!date || !file || actions.deposit.isPending}
            onClick={() =>
              file &&
              actions.deposit.mutate(
                { filing_date: date, file },
                { onSuccess: () => setFile(null), onError: fail },
              )
            }
          >
            Envoyer l’attestation au siège
          </Button>
        </Stack>
      )}
    </Section>
  );
}

// --- 5. Commission et notifications --------------------------------------------------------

const EVENT_KINDS: { value: DepositEventKind; label: string }[] = [
  { value: 'COMMISSION', label: 'Passage en commission' },
  { value: 'NOTIFICATION', label: 'Notification de l’agence' },
  { value: 'COMPLEMENT', label: 'Demande de complément' },
  { value: 'AUTRE', label: 'Autre' },
];

export function FollowSection({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const [kind, setKind] = useState<DepositEventKind>('COMMISSION');
  const [date, setDate] = useState(todayIso());
  const [note, setNote] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const decided = dossier.stage === 'OBTENU' || dossier.stage === 'REJETE';
  return (
    <Section
      index={5}
      title="Commission et notifications"
      subtitle={
        dossier.events.length
          ? `${dossier.events.length} suivi(s) noté(s) à l’agence`
          : 'Chaque passage en commission, notification ou demande de complément de l’agence.'
      }
      state={decided || dossier.stage === 'COMMISSION' ? 'done' : dossier.can.follow ? 'active' : 'todo'}
      testId="section-follow"
    >
      {dossier.events.length > 0 && (
        <Stack gap={1} sx={{ mb: 1.5 }}>
          {dossier.events.map((event) => (
            <Stack key={event.id} direction="row" gap={1.5} alignItems="flex-start">
              <Box sx={{ minWidth: 88 }}>
                <Typography variant="body2" fontWeight={700}>
                  {formatDate(event.date)}
                </Typography>
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="body2" fontWeight={600}>
                  {event.kind_label}
                </Typography>
                {event.note && (
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                    {event.note}
                  </Typography>
                )}
                <Typography variant="caption" color="text.secondary">
                  Noté par {event.created_by ?? '?'}
                </Typography>
              </Box>
              {event.has_file && (
                <Button
                  size="small"
                  startIcon={<AttachFileIcon />}
                  onClick={() =>
                    depositFiles
                      .event(dossier.id, event.id)
                      .then((blob) => saveBlob(blob, event.filename))
                      .catch(fail)
                  }
                >
                  {event.filename}
                </Button>
              )}
            </Stack>
          ))}
        </Stack>
      )}
      {dossier.can.follow && (
        <Stack gap={1}>
          <Stack direction={{ xs: 'column', md: 'row' }} gap={1}>
            <TextField
              select
              size="small"
              label="Type"
              value={kind}
              onChange={(e) => setKind(e.target.value as DepositEventKind)}
              sx={{ minWidth: 220 }}
            >
              {EVENT_KINDS.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              type="date"
              label="Date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: todayIso() } }}
            />
            <FileButton
              label={file ? file.name : 'Pièce (facultatif)'}
              accept={PIECE_ACCEPT}
              icon={<AttachFileIcon />}
              onFile={setFile}
              variant="text"
            />
          </Stack>
          <TextField
            size="small"
            label="Détail"
            placeholder="Avis de la commission, pièces demandées…"
            multiline
            minRows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <Box>
            <Button
              variant="outlined"
              disabled={!date || actions.addEvent.isPending}
              onClick={() =>
                actions.addEvent.mutate(
                  { kind, date, note, file },
                  {
                    onSuccess: () => {
                      setNote('');
                      setFile(null);
                    },
                    onError: fail,
                  },
                )
              }
            >
              Noter ce suivi
            </Button>
          </Box>
        </Stack>
      )}
    </Section>
  );
}

// --- 6. Décision ---------------------------------------------------------------------------

export function DecisionSection({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const [result, setResult] = useState<'OBTENU' | 'REJETE'>('OBTENU');
  const [form, setForm] = useState({ number: '', start_date: '', decision_date: todayIso(), note: '' });
  const [file, setFile] = useState<File | null>(null);
  const decided = dossier.stage === 'OBTENU' || dossier.stage === 'REJETE';
  const valid = form.decision_date && (result === 'REJETE' || (form.number.trim() && form.start_date));
  return (
    <Section
      index={6}
      title="Décision"
      subtitle={
        dossier.stage === 'OBTENU'
          ? `Renouvellement obtenu : n° ${dossier.renewal.number} (décision du ${formatDate(dossier.renewal.decision_date)})`
          : dossier.stage === 'REJETE'
            ? `Renouvellement rejeté le ${formatDate(dossier.renewal.decision_date)}`
            : dossier.stage === 'ABANDONNE'
              ? 'Renouvellement abandonné.'
              : 'La décision de l’agence clôt le dossier ; la fiche AMM est recalculée.'
      }
      state={decided ? 'done' : dossier.can.decide ? 'active' : 'todo'}
      testId="section-decision"
    >
      {dossier.can.decide && (
        <Stack gap={1.5}>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={result}
            onChange={(_e, value) => value && setResult(value)}
          >
            <ToggleButton value="OBTENU" color="success">
              Obtenu
            </ToggleButton>
            <ToggleButton value="REJETE" color="error">
              Rejeté
            </ToggleButton>
          </ToggleButtonGroup>
          <Stack direction={{ xs: 'column', md: 'row' }} gap={1}>
            {result === 'OBTENU' && (
              <>
                <TextField
                  size="small"
                  label="N° du renouvellement"
                  value={form.number}
                  onChange={(e) => setForm({ ...form, number: e.target.value })}
                />
                <TextField
                  size="small"
                  type="date"
                  label="Date de début"
                  value={form.start_date}
                  onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                  slotProps={{ inputLabel: { shrink: true } }}
                />
              </>
            )}
            <TextField
              size="small"
              type="date"
              label="Date de la décision"
              value={form.decision_date}
              onChange={(e) => setForm({ ...form, decision_date: e.target.value })}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <FileButton
              label={file ? file.name : 'Scan de la décision'}
              accept={SCAN_ACCEPT}
              icon={<AttachFileIcon />}
              onFile={setFile}
              variant="text"
            />
          </Stack>
          {result === 'REJETE' && (
            <TextField
              size="small"
              label="Motif"
              multiline
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          )}
          <Box>
            <Button
              variant="contained"
              color={result === 'OBTENU' ? 'success' : 'error'}
              disabled={!valid || actions.decide.isPending}
              onClick={() =>
                actions.decide.mutate(
                  {
                    result,
                    decision_date: form.decision_date,
                    ...(result === 'OBTENU'
                      ? { number: form.number.trim(), start_date: form.start_date }
                      : {}),
                    note: form.note,
                    file,
                  },
                  { onError: fail },
                )
              }
            >
              {result === 'OBTENU' ? 'Enregistrer le renouvellement obtenu' : 'Enregistrer le rejet'}
            </Button>
          </Box>
        </Stack>
      )}
    </Section>
  );
}
