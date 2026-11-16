import { depositFiles } from '@/api/hooks/useDeposits';
import type { DepositDetail, DepositEventKind } from '@/api/types';
import { DateInput } from '@/components/DateInput';
import { formatDate, todayIso } from '@/lib/dates';
import { saveBlob } from '@/lib/download';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import { Box, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { type Actions, FileButton, PIECE_ACCEPT, Section, useFail } from './sectionParts';

/** Étape 5 : commission et notifications. */

// --- 5. Commission et notifications --------------------------------------------------------

/** Types de suivi : le libellé est la clé `deposits.follow.kinds.<valeur>`. */
export const EVENT_KINDS: DepositEventKind[] = ['COMMISSION', 'NOTIFICATION', 'COMPLEMENT', 'AUTRE'];

export function FollowSection({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const { t } = useTranslation();
  const [kind, setKind] = useState<DepositEventKind>('COMMISSION');
  const [date, setDate] = useState(todayIso());
  const [note, setNote] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const decided = dossier.stage === 'OBTENU' || dossier.stage === 'REJETE';
  return (
    <Section
      index={5}
      title={t('deposits.follow.title')}
      subtitle={
        dossier.events.length
          ? t('deposits.follow.count', { n: dossier.events.length })
          : t('deposits.follow.empty')
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
                  {t('deposits.follow.recordedBy', { user: event.created_by ?? '?' })}
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
              label={t('deposits.follow.type')}
              value={kind}
              onChange={(e) => setKind(e.target.value as DepositEventKind)}
              sx={{ minWidth: 220 }}
            >
              {EVENT_KINDS.map((option) => (
                <MenuItem key={option} value={option}>
                  {t(`deposits.follow.kinds.${option}`)}
                </MenuItem>
              ))}
            </TextField>
            <DateInput
              size="small"
              fullWidth={false}
              label={t('app.date')}
              value={date}
              onChange={(value) => setDate(value ?? '')}
              maxDate={new Date()}
            />
            <FileButton
              label={file ? file.name : t('deposits.follow.fileOptional')}
              accept={PIECE_ACCEPT}
              icon={<AttachFileIcon />}
              onFile={setFile}
              variant="text"
            />
          </Stack>
          <TextField
            size="small"
            label={t('deposits.follow.detail')}
            placeholder={t('deposits.follow.detailPlaceholder')}
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
              {t('deposits.follow.record')}
            </Button>
          </Box>
        </Stack>
      )}
    </Section>
  );
}
