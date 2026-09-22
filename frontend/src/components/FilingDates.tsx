import { Stack, Typography } from '@mui/material';
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
  if (!ideal && !agency) return null;
  return (
    <Stack
      direction={direction}
      gap={direction === 'row' ? 2 : 0.5}
      flexWrap="wrap"
      data-testid="filing-dates"
    >
      <Typography variant="body2">
        Dépôt idéal : <strong>{formatDate(ideal)}</strong>
        {ideal && today > ideal ? ' (dépassé)' : ''}
      </Typography>
      <Typography variant="body2" color={agency && today > agency ? 'error' : undefined}>
        Limite agence : <strong>{formatDate(agency)}</strong>
        {agency && today > agency ? ' (dépassée)' : ''}
      </Typography>
    </Stack>
  );
}

/** Texte court d'une date de dépôt pour les tableaux : « 01/06/2026 » ou « 01/06/2026 (dépassé) ». */
export function filingDateText(value: string | null | undefined, passedLabel: string, today = todayIso()) {
  if (!value) return '—';
  return `${formatDate(value)}${today > value ? ` (${passedLabel})` : ''}`;
}
