import { useEffect, useState } from 'react';
import {
  Box,
  Chip,
  InputAdornment,
  Link as MuiLink,
  Pagination,
  Paper,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { Link } from 'react-router';
import { DOSSIER_PAGE_SIZE, useDossierCounts, useDossierImports } from '@/api/hooks/useDossierImports';
import { hasSummary, type DossierGroup, type DossierImportBatch } from '@/api/types';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { formatDateTime } from '@/lib/dates';
import { batchState } from './dossierReview';

const TABS: { value: DossierGroup; label: string; empty: string }[] = [
  { value: 'a_traiter', label: 'À traiter', empty: 'Rien à traiter : tout est rangé ou en cours.' },
  { value: 'en_cours', label: 'En cours', empty: 'Aucune analyse en cours.' },
  { value: 'ranges', label: 'Rangés', empty: 'Aucun dossier rangé.' },
  { value: 'tous', label: 'Tous', empty: 'Aucun dossier importé.' },
];

// Sur téléphone, la colonne AMM est masquée : le nom du dossier suffit et évite le défilement latéral.
const WIDE = { display: { xs: 'none', sm: 'table-cell' } } as const;
const WIDE_TEXT = { display: { xs: 'none', sm: 'inline' } } as const;
const NARROW = { display: { xs: 'inline', sm: 'none' } } as const;

/** Tape au clavier sans relancer une requête à chaque lettre. */
function useDebounced(value: string, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/**
 * Historique des dossiers importés, rangé par onglets : par défaut « À traiter » quand quelque
 * chose attend l'utilisateur, sinon « Tous ». 10 lignes par page et une recherche sur le nom.
 */
export function DossierHistory() {
  const counts = useDossierCounts();
  const [chosen, setChosen] = useState<DossierGroup | null>(null);
  const [page, setPage] = useState(1);
  const [text, setText] = useState('');
  const search = useDebounced(text.trim());
  const group: DossierGroup = chosen ?? ((counts.data?.a_traiter ?? 0) > 0 ? 'a_traiter' : 'tous');
  const batches = useDossierImports({ page, group, search }, !counts.isPending);
  const tab = TABS.find(({ value }) => value === group)!;

  return (
    <Paper variant="outlined">
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        alignItems={{ sm: 'center' }}
        justifyContent="space-between"
        gap={1}
        sx={{ px: 2, pt: 1, borderBottom: 1, borderColor: 'divider' }}
      >
        <Tabs
          value={group}
          onChange={(_, value: DossierGroup) => {
            setChosen(value);
            setPage(1);
          }}
          variant="scrollable"
          allowScrollButtonsMobile
          aria-label="Historique des dossiers importés"
        >
          {TABS.map(({ value, label }) => (
            <Tab
              key={value}
              value={value}
              sx={{ minHeight: 44, textTransform: 'none' }}
              label={
                <Stack direction="row" alignItems="center" gap={0.75}>
                  {label}
                  {counts.data && (
                    <Chip
                      size="small"
                      label={counts.data[value]}
                      color={value === 'a_traiter' && counts.data[value] ? 'warning' : 'default'}
                      sx={{ height: 20, fontSize: 12 }}
                    />
                  )}
                </Stack>
              }
            />
          ))}
        </Tabs>
        <TextField
          size="small"
          placeholder="Rechercher un dossier"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setPage(1);
          }}
          sx={{ mb: 1, minWidth: { sm: 220 } }}
          slotProps={{
            htmlInput: { 'aria-label': 'Rechercher un dossier' },
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
          }}
        />
      </Stack>
      {counts.isPending || batches.isPending ? (
        <LoadingBlock />
      ) : batches.isError ? (
        <ErrorBlock error={batches.error} onRetry={() => batches.refetch()} />
      ) : !batches.data.results.length ? (
        <EmptyBlock text={search ? `Aucun dossier ne contient « ${search} ».` : tab.empty} />
      ) : (
        <>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Dossier</TableCell>
                  <TableCell sx={WIDE}>AMM</TableCell>
                  <TableCell>Résultat</TableCell>
                  <TableCell align="right">
                    <Box component="span" sx={WIDE_TEXT}>
                      Points à vérifier
                    </Box>
                    <Box component="span" sx={NARROW}>
                      Points
                    </Box>
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {batches.data.results.map((batch) => (
                  <HistoryRow key={batch.id} batch={batch} />
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {batches.data.count > DOSSIER_PAGE_SIZE && (
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', p: 1.5 }}>
              <Typography variant="caption" color="text.secondary">
                {batches.data.count} dossiers
              </Typography>
              <Pagination
                size="small"
                page={page}
                count={Math.ceil(batches.data.count / DOSSIER_PAGE_SIZE)}
                onChange={(_, value) => setPage(value)}
              />
            </Box>
          )}
        </>
      )}
    </Paper>
  );
}

function HistoryRow({ batch }: { batch: DossierImportBatch }) {
  const state = batchState(batch);
  const ammId = hasSummary(batch.summary) ? batch.summary.amm_id : batch.amm_id;
  const ammLabel = hasSummary(batch.summary)
    ? `${batch.summary.product} (${batch.summary.country_iso2})`
    : batch.preview?.amm?.product_name
      ? `${batch.preview.amm.product_name}${batch.preview.amm.country_iso2 ? ` (${batch.preview.amm.country_iso2})` : ''}`
      : '—';
  return (
    <TableRow hover>
      <TableCell>
        <MuiLink component={Link} to={`/dossier-imports/${batch.id}`}>
          {batch.root_name}
        </MuiLink>
        <Typography variant="caption" display="block" color="text.secondary">
          {formatDateTime(batch.created_at)}
        </Typography>
      </TableCell>
      <TableCell sx={WIDE}>
        {ammId && batch.status === 'APPLIED' ? (
          <MuiLink component={Link} to={`/amms/${ammId}`}>
            {ammLabel}
          </MuiLink>
        ) : batch.status === 'QUESTION' ? (
          <Typography variant="body2" color="text.secondary">
            À préciser
          </Typography>
        ) : (
          ammLabel
        )}
      </TableCell>
      <TableCell>
        <Chip
          size="small"
          label={state.label}
          color={state.tone}
          variant={batch.status === 'APPLIED' ? 'filled' : 'outlined'}
        />
      </TableCell>
      <TableCell align="right">
        {batch.open_points_count ? (
          <Chip
            size="small"
            color="warning"
            variant="outlined"
            label={batch.open_points_count}
            aria-label={`${batch.open_points_count} point(s) à vérifier`}
          />
        ) : (
          '—'
        )}
      </TableCell>
    </TableRow>
  );
}
