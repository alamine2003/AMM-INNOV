import { Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { formatDate, todayIso } from '@/lib/dates';

/**
 * « Dépôt idéal : jj/mm/aaaa » (fin − 6 mois, objectif interne) et « Limite agence :
 * jj/mm/aaaa » (fin − 3 mois), avec la mention « dépassé(e) » une fois la date passée.
 */
export function FilingDates({
  ideal,
  agency,
  direction = 'row',
  today = todayIso(),
}: {
  ideal: string | null | undefined;
  agency: string | null | undefined;
  direction?: 'row' | 'column';
  today?: string;
}) {
  const { t } = useTranslation();
  if (!ideal && !agency) return null;
  return (
    <Stack
      direction={direction}
      gap={direction === 'row' ? 2 : 0.5}
      flexWrap="wrap"
      data-testid="filing-dates"
    >
      <Typography variant="body2">
        {t('common.filingDates.ideal')} <strong>{formatDate(ideal)}</strong>
        {ideal && today > ideal ? ` (${t('common.filingDates.passedIdeal')})` : ''}
      </Typography>
      <Typography variant="body2" color={agency && today > agency ? 'error' : undefined}>
        {t('common.filingDates.agency')} <strong>{formatDate(agency)}</strong>
        {agency && today > agency ? ` (${t('common.filingDates.passedAgency')})` : ''}
      </Typography>
    </Stack>
  );
}

/** Texte court d'une date de dépôt pour les tableaux : « 01/06/2026 » ou « 01/06/2026 (dépassé) ». */
export function filingDateText(value: string | null | undefined, passedLabel: string, today = todayIso()) {
  if (!value) return '—';
  return `${formatDate(value)}${today > value ? ` (${passedLabel})` : ''}`;
}
