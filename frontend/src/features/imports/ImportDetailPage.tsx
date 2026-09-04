import { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Grid2 as Grid,
  LinearProgress,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from '@mui/material';
import { useParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useImport, useImportRows } from '@/api/hooks/useImports';
import { PageHeader } from '@/components/PageHeader';
import { KpiCard } from '@/components/KpiCard';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { formatDateTime } from '@/lib/dates';
import { statusColor } from './ImportsPage';

export default function ImportDetailPage() {
  const { id = '' } = useParams();
  const { t } = useTranslation();
  const batch = useImport(id, true);
  const [page, setPage] = useState(1);
  const rows = useImportRows(id, 'ERROR', page, 25);

  if (batch.isPending) return <LoadingBlock />;
  if (batch.isError) return <ErrorBlock error={batch.error} onRetry={() => batch.refetch()} />;
  const b = batch.data;
  const s = (b.summary ?? {}) as Record<string, unknown>;
  const running = b.status === 'RUNNING' || b.status === 'PENDING';
  const sheets = (s.sheets ?? {}) as Record<string, Record<string, number>>;

  return (
    <Box>
      <PageHeader
        title={b.file_name ?? b.id}
        subtitle={
          <>
            <Chip size="small" label={b.status} color={statusColor(b.status)} sx={{ mr: 1 }} />
            {formatDateTime(b.created_at)}
          </>
        }
      />
      {running && <LinearProgress sx={{ mb: 2 }} />}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          ['created', t('admin.imports.created'), '#2e7d32'],
          ['updated', t('admin.imports.updated'), '#1565c0'],
          ['skipped', t('admin.imports.skipped'), '#757575'],
          ['errors', t('admin.imports.errorCount'), '#c62828'],
          ['warnings', t('admin.imports.warnings'), '#ef6c00'],
        ].map(([key, label, color]) => (
          <Grid key={key} size={{ xs: 6, sm: 4, md: 2.4 }}>
            <KpiCard
              label={label}
              value={typeof s[key] === 'number' ? (s[key] as number) : '—'}
              color={color}
            />
          </Grid>
        ))}
      </Grid>
      {Object.keys(sheets).length > 0 && (
        <Card variant="outlined" sx={{ mb: 3 }}>
          <CardHeader title={t('admin.imports.summary')} titleTypographyProps={{ variant: 'h6' }} />
          <CardContent sx={{ pt: 0 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('admin.imports.sheet')}</TableCell>
                  <TableCell align="right">{t('admin.imports.created')}</TableCell>
                  <TableCell align="right">{t('admin.imports.updated')}</TableCell>
                  <TableCell align="right">{t('admin.imports.errorCount')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {Object.entries(sheets).map(([name, v]) => (
                  <TableRow key={name}>
                    <TableCell>{name}</TableCell>
                    <TableCell align="right">{v.created ?? 0}</TableCell>
                    <TableCell align="right">{v.updated ?? 0}</TableCell>
                    <TableCell align="right">{v.errors ?? 0}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
      <Typography variant="h6" gutterBottom>
        {t('admin.imports.errors')}
      </Typography>
      <Paper variant="outlined">
        {rows.isPending && <LoadingBlock />}
        {rows.data && rows.data.results.length === 0 && <EmptyBlock text={t('admin.imports.noErrors')} />}
        {rows.data && rows.data.results.length > 0 && (
          <>
            <TableContainer sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('admin.imports.sheet')}</TableCell>
                    <TableCell>{t('admin.imports.row')}</TableCell>
                    <TableCell>{t('admin.imports.message')}</TableCell>
                    <TableCell>{t('admin.imports.raw')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.data.results.map((r, i) => (
                    <TableRow key={`${r.sheet}-${r.row_number}-${i}`}>
                      <TableCell>{r.sheet}</TableCell>
                      <TableCell>{r.row_number}</TableCell>
                      <TableCell sx={{ color: 'error.main' }}>{r.message}</TableCell>
                      <TableCell>
                        <Typography
                          variant="caption"
                          component="pre"
                          sx={{ m: 0, whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}
                        >
                          {Object.entries(r.raw)
                            .map(([k, v]) => `${k}: ${String(v ?? '')}`)
                            .join('\n')}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              component="div"
              count={rows.data.count}
              page={page - 1}
              rowsPerPage={25}
              rowsPerPageOptions={[25]}
              onPageChange={(_e, p) => setPage(p + 1)}
            />
          </>
        )}
      </Paper>
    </Box>
  );
}
