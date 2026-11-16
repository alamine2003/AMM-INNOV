import { useState, type ReactNode } from 'react';
import { Box, Button } from '@mui/material';
import { useTranslation } from 'react-i18next';

/**
 * Liste courte par défaut : les `limit` premiers éléments, puis « Voir tout (N) » à la demande.
 * Évite les longs défilements quand un import touche des centaines de dossiers.
 */
export function CappedList<T>({
  items,
  render,
  itemKey,
  limit = 5,
}: {
  items: T[];
  render: (item: T) => ReactNode;
  itemKey: (item: T, index: number) => string;
  limit?: number;
}) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, limit);
  return (
    <>
      <Box component="ul" sx={{ m: 0, pl: 2 }}>
        {shown.map((item, index) => (
          <li key={itemKey(item, index)}>{render(item)}</li>
        ))}
      </Box>
      {items.length > limit && (
        <Button size="small" sx={{ mt: 0.5, px: 0.5 }} onClick={() => setAll(!all)}>
          {all
            ? t('dossierImports.cappedList.collapse')
            : t('dossierImports.cappedList.showAll', { count: items.length })}
        </Button>
      )}
    </>
  );
}
