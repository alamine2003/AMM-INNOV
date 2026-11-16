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
  Tooltip,
  Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { DOSSIER_PAGE_SIZE, useDossierCounts, useDossierImports } from '@/api/hooks/useDossierImports';
import { hasSummary, type DossierGroup, type DossierImportBatch } from '@/api/types';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { formatDateTime } from '@/lib/dates';
import { batchState } from './dossierReview';

// Clés de traduction : le libellé est résolu au rendu pour suivre la langue.
const TABS: { value: DossierGroup; label: string; empty: string }[] = [
  {
    value: 'a_traiter',
    label: 'dossierImports.history.tabs.toProcess.label',
    empty: 'dossierImports.history.tabs.toProcess.empty',
  },
  {
    value: 'en_cours',
    label: 'dossierImports.history.tabs.inProgress.label',
    empty: 'dossierImports.history.tabs.inProgress.empty',
  },
  {
    value: 'ranges',
    label: 'dossierImports.history.tabs.filed.label',
    empty: 'dossierImports.history.tabs.filed.empty',
  },
  { value: 'tous', label: 'app.all', empty: 'dossierImports.history.tabs.all.empty' },
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
  const { t } = useTranslation();
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
          aria-label={t('dossierImports.history.ariaLabel')}
        >
          {TABS.map(({ value, label }) => (
            <Tab
              key={value}
              value={value}
              sx={{ minHeight: 44, textTransform: 'none' }}
              label={
                <Stack direction="row" alignItems="center" gap={0.75}>
                  {t(label)}
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
          placeholder={t('dossierImports.history.searchPlaceholder')}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setPage(1);
          }}
          sx={{ mb: 1, minWidth: { sm: 220 } }}
          slotProps={{
            htmlInput: { 'aria-label': t('dossierImports.history.searchPlaceholder') },
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
        <EmptyBlock text={search ? t('dossierImports.history.noMatch', { search }) : t(tab.empty)} />
      ) : (
        <>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('dossierImports.columns.dossier')}</TableCell>
                  <TableCell sx={WIDE}>{t('dossierImports.columns.ma')}</TableCell>
                  <TableCell>{t('dossierImports.columns.result')}</TableCell>
                  <TableCell align="right">
                    <Box component="span" sx={WIDE_TEXT}>
                      {t('dossierImports.columns.pointsToCheck')}
                    </Box>
                    <Box component="span" sx={NARROW}>
                      {t('dossierImports.columns.points')}
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
                {t('dossierImports.history.total', { count: batches.data.count })}
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
  const { t } = useTranslation();
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
            {t('dossierImports.history.toSpecify')}
          </Typography>
        ) : (
          ammLabel
        )}
      </TableCell>
      <TableCell>
        <Tooltip title={batch.status_reason ?? ''}>
          <Chip
            size="small"
            label={state.label}
            color={state.tone}
            variant={batch.status === 'APPLIED' ? 'filled' : 'outlined'}
          />
        </Tooltip>
        {batch.status_reason && batch.status !== 'QUESTION' && (
          // Pas rangé : la raison est toujours dite, sans ouvrir le dossier.
          <Typography variant="caption" display="block" color="text.secondary" sx={{ maxWidth: 280 }}>
            {batch.status_reason}
          </Typography>
        )}
      </TableCell>
      <TableCell align="right">
        {batch.open_points_count ? (
          <Chip
            size="small"
            color="warning"
            variant="outlined"
            label={batch.open_points_count}
            aria-label={t('dossierImports.history.pointsAria', { count: batch.open_points_count })}
          />
        ) : (
          '—'
        )}
      </TableCell>
    </TableRow>
  );
}
