import { depositFiles } from '@/api/hooks/useDeposits';
import type { DepositDetail } from '@/api/types';
import { formatDateTime } from '@/lib/dates';
import { saveBlob } from '@/lib/download';
import DownloadIcon from '@mui/icons-material/Download';
import SendIcon from '@mui/icons-material/Send';
import { Alert, Box, Button, Stack, TextField, Typography } from '@mui/material';
import { useState } from 'react';
import { type Actions, Section, useFail } from './sectionParts';

/** Étape 3 : l'envoi au pays. */

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
