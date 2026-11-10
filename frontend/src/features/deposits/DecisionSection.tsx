import type { DepositDetail } from '@/api/types';
import { DateInput } from '@/components/DateInput';
import { formatDate, todayIso } from '@/lib/dates';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import { Box, Button, Stack, TextField, ToggleButton, ToggleButtonGroup } from '@mui/material';
import { useState } from 'react';
import { type Actions, FileButton, SCAN_ACCEPT, Section, useFail } from './sectionParts';

/** Étape 6 : la décision. */

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
                <DateInput
                  size="small"
                  fullWidth={false}
                  label="Date de début"
                  value={form.start_date}
                  onChange={(value) => setForm({ ...form, start_date: value ?? '' })}
                />
              </>
            )}
            <DateInput
              size="small"
              fullWidth={false}
              label="Date de la décision"
              value={form.decision_date}
              onChange={(value) => setForm({ ...form, decision_date: value ?? '' })}
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
