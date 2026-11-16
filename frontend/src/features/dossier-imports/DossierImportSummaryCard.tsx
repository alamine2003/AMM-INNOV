import { Alert, Box, Button, Chip, Paper, Stack, Typography } from '@mui/material';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import type { DossierImportSummary } from '@/api/types';

const fr = (value: string | null | undefined) =>
  value ? value.slice(0, 10).split('-').reverse().join('/') : '—';

function Change({ label, before, after }: { label: string; before?: string; after: string }) {
  const changed = before !== undefined && before !== after;
  return (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
      <Typography variant="body2" sx={{ minWidth: 110 }} color="text.secondary">
        {label}
      </Typography>
      {changed && (
        <>
          <Chip size="small" variant="outlined" label={before} />
          <Typography variant="body2">→</Typography>
        </>
      )}
      <Chip size="small" color={changed ? 'primary' : 'default'} label={after} />
    </Stack>
  );
}

/** Ce que la validation a réellement changé sur l'AMM (bilan calculé côté serveur après commit). */
export function DossierImportSummaryCard({ summary }: { summary: DossierImportSummary }) {
  const { t } = useTranslation();
  const statusLabel = (value: string) => t(`status.${value}`, { defaultValue: value });
  const dossierLabel = (value: string) => t(`dossierImports.dossierStates.${value}`, { defaultValue: value });
  const empty = t('dossierImports.values.empty');
  const before = summary.before;
  const after = summary.after;
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h6">{t('dossierImports.summary.title')}</Typography>
        <Button component={Link} to={`/amms/${summary.amm_id}`} size="small">
          {summary.product} ({summary.country_iso2})
        </Button>
      </Stack>
      {summary.created && (
        <Typography variant="body2" sx={{ mb: 1 }}>
          {t('dossierImports.summary.created')}
        </Typography>
      )}
      <Stack spacing={1} sx={{ my: 2 }}>
        <Change
          label={t('admin.imports.status')}
          before={before ? statusLabel(before.status) : undefined}
          after={statusLabel(after.status)}
        />
        <Change
          label={t('dossierImports.columns.dossier')}
          before={before ? dossierLabel(before.dossier_state) : undefined}
          after={dossierLabel(after.dossier_state)}
        />
        <Change
          label={t('dossierImports.summary.expiry')}
          before={before ? fr(before.effective_end_date) : undefined}
          after={fr(after.effective_end_date)}
        />
      </Stack>
      {summary.renewals_created.length > 0 && (
        <Box sx={{ mb: 1 }}>
          <Typography variant="subtitle2">{t('dossierImports.summary.renewalsAdded')}</Typography>
          {summary.renewals_created.map((r) => (
            <Typography key={`${r.number}-${r.start_date}`} variant="body2">
              {t('dossierImports.summary.renewalLine', {
                number: r.number || '?',
                start: fr(r.start_date),
                end: fr(r.end_date),
              })}
            </Typography>
          ))}
        </Box>
      )}
      {summary.fields_changed.length > 0 && (
        <Box sx={{ mb: 1 }}>
          <Typography variant="subtitle2">{t('dossierImports.summary.fieldsChanged')}</Typography>
          {summary.fields_changed.map((f, i) => (
            <Typography key={`${f.field}-${i}`} variant="body2">
              {t('dossierImports.summary.fieldLine', {
                label: f.label,
                old: f.old === null || f.old === '' ? empty : String(f.old),
                new: String(f.new),
              })}
            </Typography>
          ))}
        </Box>
      )}
      <Typography variant="body2" color="text.secondary">
        {t('dossierImports.summary.documents', { count: summary.documents.length })}
      </Typography>
      {summary.missing_scan && (
        <Alert severity="warning" sx={{ mt: 2 }}>
          {t('dossierImports.summary.stillIncomplete', { scan: summary.missing_scan })}
        </Alert>
      )}
    </Paper>
  );
}
