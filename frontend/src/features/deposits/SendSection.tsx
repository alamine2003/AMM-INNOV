import { depositFiles } from '@/api/hooks/useDeposits';
import type { DepositDetail } from '@/api/types';
import { formatDateTime } from '@/lib/dates';
import { saveBlob } from '@/lib/download';
import DownloadIcon from '@mui/icons-material/Download';
import SendIcon from '@mui/icons-material/Send';
import { Alert, Box, Button, Stack, TextField, Typography } from '@mui/material';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { type Actions, Section, useFail } from './sectionParts';

/** Étape 3 : l'envoi au pays. */

// --- 3. Envoi au pays ----------------------------------------------------------------------

export function SendSection({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const { t } = useTranslation();
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
      {downloading ? t('deposits.send.preparing') : label}
    </Button>
  );
  const countryDownloads = dossier.downloads;
  return (
    <Section
      index={3}
      title={t('deposits.send.title')}
      subtitle={
        dossier.sent_at
          ? dossier.sent_by
            ? t('deposits.send.sentBy', { date: formatDateTime(dossier.sent_at), user: dossier.sent_by })
            : t('deposits.send.sent', { date: formatDateTime(dossier.sent_at) })
          : t('deposits.send.pending')
      }
      state={dossier.sent_at ? 'done' : dossier.can.manage ? 'active' : 'todo'}
      testId="section-send"
    >
      {!dossier.sent_at && dossier.can.manage && (
        <Stack gap={1.5}>
          {dossier.missing.length > 0 ? (
            <Alert severity="warning">
              <strong>{t('deposits.send.beforeSend')}</strong> {dossier.missing.join(' ; ')}.
            </Alert>
          ) : (
            <Alert severity="success">{t('deposits.send.complete')}</Alert>
          )}
          <TextField
            label={t('deposits.send.noteLabel')}
            placeholder={t('deposits.send.notePlaceholder')}
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
              {t('deposits.send.sendButton')}
            </Button>
            {zipButton(t('deposits.send.preview'), 'outlined')}
          </Stack>
        </Stack>
      )}
      {dossier.sent_at && (
        <Stack gap={1}>
          {dossier.send_note && (
            <Alert severity="info" icon={false}>
              <strong>{t('deposits.send.hqMessage')}</strong> {dossier.send_note}
            </Alert>
          )}
          <Box>{zipButton(t('deposits.send.download'))}</Box>
          <Typography variant="body2" color="text.secondary" data-testid="downloads">
            {countryDownloads.length
              ? t('deposits.send.downloaded', {
                  n: countryDownloads.length,
                  user: countryDownloads[0].user ?? '?',
                  date: formatDateTime(countryDownloads[0].at),
                })
              : t('deposits.send.notDownloaded')}
          </Typography>
        </Stack>
      )}
    </Section>
  );
}
