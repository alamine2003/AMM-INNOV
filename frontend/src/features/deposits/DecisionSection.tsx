import type { DepositDetail } from '@/api/types';
import { DateInput } from '@/components/DateInput';
import { formatDate, todayIso } from '@/lib/dates';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import { Box, Button, Stack, TextField, ToggleButton, ToggleButtonGroup } from '@mui/material';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { type Actions, FileButton, SCAN_ACCEPT, Section, useFail } from './sectionParts';

/** Étape 6 : la décision. */

// --- 6. Décision ---------------------------------------------------------------------------

export function DecisionSection({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const { t } = useTranslation();
  const [result, setResult] = useState<'OBTENU' | 'REJETE'>('OBTENU');
  const [form, setForm] = useState({ number: '', start_date: '', decision_date: todayIso(), note: '' });
  const [file, setFile] = useState<File | null>(null);
  const decided = dossier.stage === 'OBTENU' || dossier.stage === 'REJETE';
  // Demande d'AMM d'origine (1.4.1) : la décision donne le n° et les dates de l'AMM elle-même.
  const origin = dossier.renewal === null;
  const valid = form.decision_date && (result === 'REJETE' || (form.number.trim() && form.start_date));
  return (
    <Section
      index={6}
      title={t('deposits.decision.title')}
      subtitle={
        dossier.stage === 'OBTENU'
          ? dossier.renewal
            ? t('deposits.decision.granted', {
                number: dossier.renewal.number,
                date: formatDate(dossier.renewal.decision_date),
              })
            : t('deposits.decision.grantedOrigin', { number: dossier.amm.original_number })
          : dossier.stage === 'REJETE'
            ? dossier.renewal
              ? t('deposits.decision.rejected', { date: formatDate(dossier.renewal.decision_date) })
              : t('deposits.decision.rejectedOrigin')
            : dossier.stage === 'ABANDONNE'
              ? t(origin ? 'deposits.decision.withdrawnOrigin' : 'deposits.decision.withdrawn')
              : t('deposits.decision.pending')
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
              {t('deposits.decision.optGranted')}
            </ToggleButton>
            <ToggleButton value="REJETE" color="error">
              {t('deposits.decision.optRejected')}
            </ToggleButton>
          </ToggleButtonGroup>
          <Stack direction={{ xs: 'column', md: 'row' }} gap={1}>
            {result === 'OBTENU' && (
              <>
                <TextField
                  size="small"
                  label={t(origin ? 'deposits.decision.ammNumber' : 'deposits.decision.renewalNumber')}
                  value={form.number}
                  onChange={(e) => setForm({ ...form, number: e.target.value })}
                />
                <DateInput
                  size="small"
                  fullWidth={false}
                  label={t('deposits.decision.startDate')}
                  value={form.start_date}
                  onChange={(value) => setForm({ ...form, start_date: value ?? '' })}
                />
              </>
            )}
            <DateInput
              size="small"
              fullWidth={false}
              label={t('deposits.decision.decisionDate')}
              value={form.decision_date}
              onChange={(value) => setForm({ ...form, decision_date: value ?? '' })}
            />
            <FileButton
              label={file ? file.name : t('deposits.decision.scan')}
              accept={SCAN_ACCEPT}
              icon={<AttachFileIcon />}
              onFile={setFile}
              variant="text"
            />
          </Stack>
          {result === 'REJETE' && (
            <TextField
              size="small"
              label={t('deposits.decision.reason')}
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
              {result === 'OBTENU'
                ? t(origin ? 'deposits.decision.saveGrantedOrigin' : 'deposits.decision.saveGranted')
                : t('deposits.decision.saveRejected')}
            </Button>
          </Box>
        </Stack>
      )}
    </Section>
  );
}
