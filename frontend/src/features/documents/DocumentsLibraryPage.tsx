import { useMemo, useState } from 'react';
import {
  Box,
  FormControl,
  IconButton,
  InputLabel,
  Link as MuiLink,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import DownloadIcon from '@mui/icons-material/Download';
import { Link, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useCountries } from '@/api/hooks/useCatalog';
import { documentFileName, fetchDocumentBlob, useCountryDocuments } from '@/api/hooks/useDocuments';
import type { AmmDocument } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { formatDate } from '@/lib/dates';
import { formatBytes, saveBlob } from '@/lib/download';
import { extractErrorMessage } from '@/api/client';
import { useAuthStore } from '@/features/auth/authStore';
import { PdfViewerDialog } from './PdfViewerDialog';

const KINDS = ['AMM', 'RECEPISSE', 'COURRIER', 'AUTRE'];

export default function DocumentsLibraryPage() {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const [sp, setSp] = useSearchParams();
  const user = useAuthStore((s) => s.user);
  const countries = useCountries();
  const visible = useMemo(
    () =>
      (countries.data ?? []).filter(
        (c) => user?.role !== 'COUNTRY_REGULATORY' || user.countries.includes(c.iso2),
      ),
    [countries.data, user],
  );
  const country = sp.get('country') ?? visible[0]?.iso2 ?? '';
  const kind = sp.get('kind') ?? '';
  const year = sp.get('year') ?? '';
  const [viewing, setViewing] = useState<AmmDocument | null>(null);

  const docs = useCountryDocuments(country || undefined, { kind, year });
  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(sp);
    next.set('country', country);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setSp(next);
  };

  const years = useMemo(() => {
    const now = new Date().getFullYear();
    return Array.from({ length: 15 }, (_, i) => String(now - i));
  }, []);

  const sorted = useMemo(
    () =>
      [...(docs.data ?? [])].sort(
        (a, b) =>
          b.document_date.localeCompare(a.document_date) || b.uploaded_at.localeCompare(a.uploaded_at),
      ),
    [docs.data],
  );

  const download = async (d: AmmDocument) => {
    try {
      saveBlob(await fetchDocumentBlob(d.id, true), documentFileName(d, d.country_iso2, d.product_name));
    } catch (e) {
      enqueueSnackbar(extractErrorMessage(e), { variant: 'error' });
    }
  };

  return (
    <Box>
      <PageHeader title={t('documents.library')} subtitle={t('documents.librarySubtitle')} />
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel id="lib-country">{t('documents.filters.country')}</InputLabel>
          <Select
            labelId="lib-country"
            label={t('documents.filters.country')}
            value={country}
            onChange={(e) => set({ country: e.target.value })}
          >
            {visible.map((c) => (
              <MenuItem key={c.iso2} value={c.iso2}>
                {c.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel id="lib-kind">{t('documents.filters.kind')}</InputLabel>
          <Select
            labelId="lib-kind"
            label={t('documents.filters.kind')}
            value={kind}
            onChange={(e) => set({ kind: e.target.value })}
          >
            <MenuItem value="">{t('app.all')}</MenuItem>
            {KINDS.map((k) => (
              <MenuItem key={k} value={k}>
                {t(`documentKind.${k}`)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel id="lib-year">{t('documents.filters.year')}</InputLabel>
          <Select
            labelId="lib-year"
            label={t('documents.filters.year')}
            value={year}
            onChange={(e) => set({ year: e.target.value })}
          >
            <MenuItem value="">{t('app.all')}</MenuItem>
            {years.map((y) => (
              <MenuItem key={y} value={y}>
                {y}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>
      {!country && <Typography color="text.secondary">{t('documents.selectCountry')}</Typography>}
      {country && docs.isPending && <LoadingBlock />}
      {country && docs.isError && <ErrorBlock error={docs.error} onRetry={() => docs.refetch()} />}
      {country && docs.data && (
        <Paper variant="outlined">
          {sorted.length === 0 ? (
            <EmptyBlock text={t('documents.empty')} />
          ) : (
            <TableContainer sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('documents.columns.date')}</TableCell>
                    <TableCell>{t('documents.columns.kind')}</TableCell>
                    <TableCell>{t('documents.columns.title')}</TableCell>
                    <TableCell>{t('documents.columns.product')}</TableCell>
                    <TableCell>{t('documents.columns.size')}</TableCell>
                    <TableCell>{t('documents.columns.uploadedBy')}</TableCell>
                    <TableCell align="right">{t('app.actions')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sorted.map((d) => (
                    <TableRow key={d.id} hover>
                      <TableCell>{formatDate(d.document_date)}</TableCell>
                      <TableCell>{t(`documentKind.${d.kind}`)}</TableCell>
                      <TableCell>{d.title}</TableCell>
                      <TableCell>
                        <MuiLink component={Link} to={`/amms/${d.amm_id}?tab=documents`} underline="hover">
                          {d.product_name}
                        </MuiLink>
                      </TableCell>
                      <TableCell>{formatBytes(d.size_bytes)}</TableCell>
                      <TableCell>{d.uploaded_by_email}</TableCell>
                      <TableCell align="right">
                        <Tooltip title={t('documents.view')}>
                          <IconButton size="small" onClick={() => setViewing(d)}>
                            <VisibilityIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title={t('app.download')}>
                          <IconButton size="small" onClick={() => download(d)}>
                            <DownloadIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Paper>
      )}
      <PdfViewerDialog doc={viewing} open={!!viewing} onClose={() => setViewing(null)} />
    </Box>
  );
}
