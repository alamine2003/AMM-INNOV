import type { DepositDetail } from '@/api/types';
import { DateInput } from '@/components/DateInput';
import { formatDate } from '@/lib/dates';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import {
  Button,
  FormControlLabel,
  IconButton,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
} from '@mui/material';
import { useState } from 'react';
import { type Actions, Section, useFail } from './sectionParts';

/** Étape 2 : les échantillons. */

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
          <DateInput
            size="small"
            fullWidth={false}
            label="Date de fabrication"
            value={form.manufactured_on}
            onChange={(value) => setForm({ ...form, manufactured_on: value ?? '' })}
          />
          <DateInput
            size="small"
            fullWidth={false}
            label="Date de péremption"
            value={form.expires_on}
            onChange={(value) => setForm({ ...form, expires_on: value ?? '' })}
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
