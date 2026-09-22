import { Alert, Box, Button, Chip, Paper, Stack, Typography } from '@mui/material';
import { Link } from 'react-router';

import type { DossierImportSummary } from '@/api/types';

const statusLabels: Record<string, string> = {
  VALIDE: 'Valide',
  EXPIRE: 'Expirée',
  IN_PROCESS: 'En cours',
  INDETERMINE: 'Indéterminé',
};
const dossierLabels: Record<string, string> = { COMPLET: 'Complet', INCOMPLET: 'Incomplet' };

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
  const before = summary.before;
  const after = summary.after;
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h6">Ce que l’import a changé</Typography>
        <Button component={Link} to={`/amms/${summary.amm_id}`} size="small">
          {summary.product} ({summary.country_iso2})
        </Button>
      </Stack>
      {summary.created && (
        <Typography variant="body2" sx={{ mb: 1 }}>
          AMM créée à partir du dossier.
        </Typography>
      )}
      <Stack spacing={1} sx={{ my: 2 }}>
        <Change
          label="Statut"
          before={before ? (statusLabels[before.status] ?? before.status) : undefined}
          after={statusLabels[after.status] ?? after.status}
        />
        <Change
          label="Dossier"
          before={before ? (dossierLabels[before.dossier_state] ?? before.dossier_state) : undefined}
          after={dossierLabels[after.dossier_state] ?? after.dossier_state}
        />
        <Change
          label="Échéance"
          before={before ? fr(before.effective_end_date) : undefined}
          after={fr(after.effective_end_date)}
        />
      </Stack>
      {summary.renewals_created.length > 0 && (
        <Box sx={{ mb: 1 }}>
          <Typography variant="subtitle2">Renouvellements ajoutés</Typography>
          {summary.renewals_created.map((r) => (
            <Typography key={`${r.number}-${r.start_date}`} variant="body2">
              N° {r.number || '?'} : {fr(r.start_date)} → {fr(r.end_date)}
            </Typography>
          ))}
        </Box>
      )}
      {summary.fields_changed.length > 0 && (
        <Box sx={{ mb: 1 }}>
          <Typography variant="subtitle2">Champs modifiés</Typography>
          {summary.fields_changed.map((f, i) => (
            <Typography key={`${f.field}-${i}`} variant="body2">
              {f.label} : {f.old === null || f.old === '' ? 'vide' : String(f.old)} → {String(f.new)}
            </Typography>
          ))}
        </Box>
      )}
      <Typography variant="body2" color="text.secondary">
        {summary.documents.length} document(s) rattaché(s) à la fiche AMM.
      </Typography>
      {summary.missing_scan && (
        <Alert severity="warning" sx={{ mt: 2 }}>
          Dossier toujours incomplet : il manque le {summary.missing_scan}.
        </Alert>
      )}
    </Paper>
  );
}
