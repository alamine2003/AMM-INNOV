import { fetchBlob } from '@/api/client';
import type { DepositDetail } from '@/api/types';
import { DateInput } from '@/components/DateInput';
import { formatDate, todayIso } from '@/lib/dates';
import { saveBlob } from '@/lib/download';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import SendIcon from '@mui/icons-material/Send';
import { Button, Stack } from '@mui/material';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { type Actions, FileButton, SCAN_ACCEPT, Section, useFail } from './sectionParts';

/** Étape 4 : le dépôt à l'agence. */

// --- 4. Dépôt à l'agence -------------------------------------------------------------------

export function DepositSection({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const { t } = useTranslation();
  const [date, setDate] = useState(todayIso());
  const [file, setFile] = useState<File | null>(null);
  const deposited =
    !!dossier.renewal.filing_date && ['DEPOSE', 'COMMISSION', 'OBTENU', 'REJETE'].includes(dossier.stage);
  const authority = dossier.amm.authority || t('deposits.defaultAuthority');
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
      title={t('deposits.submit.title')}
      subtitle={
        deposited
          ? t('deposits.submit.done', { authority, date: formatDate(dossier.renewal.filing_date) })
          : t('deposits.submit.pending', { authority })
      }
      state={deposited ? 'done' : dossier.sent_at ? 'active' : 'todo'}
      testId="section-deposit"
    >
      {deposited && dossier.attestation && (
        <Button size="small" startIcon={<AttachFileIcon />} onClick={openAttestation}>
          {t('deposits.submit.receiptOf', { date: formatDate(dossier.attestation.document_date) })}
        </Button>
      )}
      {!deposited && dossier.can.deposit && (
        <Stack direction={{ xs: 'column', md: 'row' }} gap={1} alignItems={{ md: 'center' }}>
          <DateInput
            size="small"
            fullWidth={false}
            label={t('deposits.submit.date')}
            value={date}
            onChange={(value) => setDate(value ?? '')}
            maxDate={new Date()}
          />
          <FileButton
            label={file ? file.name : t('deposits.submit.receiptFile')}
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
            {t('deposits.submit.sendReceipt')}
          </Button>
        </Stack>
      )}
    </Section>
  );
}
