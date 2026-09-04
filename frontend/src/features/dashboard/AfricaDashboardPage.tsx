import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Grid2 as Grid,
  Link as MuiLink,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useAfricaAnalytics } from '@/api/hooks/useAnalytics';
import { useAmms } from '@/api/hooks/useAmms';
import { PageHeader } from '@/components/PageHeader';
import { KpiCard } from '@/components/KpiCard';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { STATUS_COLORS, URGENCY_ORDER } from '@/lib/urgency';
import type { AfricaRow } from '@/api/types';
import { PrioritiesTable } from './PrioritiesTable';

const pct = (v: number) => `${Math.round(v)} %`;

function AfricaTable({ rows, total }: { rows: AfricaRow[]; total: AfricaRow }) {
  const { t } = useTranslation();
  const cols: { key: keyof AfricaRow; label: string; fmt?: (v: number) => string }[] = [
    { key: 'total', label: t('dashboard.table.total') },
    { key: 'valid', label: t('dashboard.table.valid') },
    { key: 'expired', label: t('dashboard.table.expired') },
    { key: 'in_process', label: t('dashboard.table.inProcess') },
    { key: 'undetermined', label: t('dashboard.table.undetermined') },
    { key: 'pct_valid', label: t('dashboard.table.pctValid'), fmt: pct },
    { key: 'expiring_6m', label: t('dashboard.table.expiring6m') },
    { key: 'expiring_12m', label: t('dashboard.table.expiring12m') },
    { key: 'pct_complete', label: t('dashboard.table.pctComplete'), fmt: pct },
  ];
  const render = (row: AfricaRow, isTotal = false) => (
    <TableRow
      key={row.country_iso2}
      sx={isTotal ? { '& td': { fontWeight: 700, bgcolor: '#eef2f6' } } : undefined}
      data-testid={isTotal ? 'africa-total-row' : `africa-row-${row.country_iso2}`}
    >
      <TableCell>
        {isTotal ? (
          t('app.total')
        ) : (
          <MuiLink component={Link} to={`/countries/${row.country_iso2}`} underline="hover" fontWeight={600}>
            {row.country_name}
          </MuiLink>
        )}
      </TableCell>
      {cols.map((c) => (
        <TableCell key={c.key} align="right">
          {c.fmt ? c.fmt(Number(row[c.key])) : String(row[c.key])}
        </TableCell>
      ))}
    </TableRow>
  );
  return (
    <TableContainer sx={{ overflowX: 'auto' }}>
      <Table size="small" data-testid="africa-table">
        <TableHead>
          <TableRow>
            <TableCell>{t('dashboard.table.country')}</TableCell>
            {cols.map((c) => (
              <TableCell key={c.key} align="right">
                {c.label}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => render(r))}
          {render(total, true)}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

export default function AfricaDashboardPage() {
  const { t } = useTranslation();
  const analytics = useAfricaAnalytics();
  const priorities = useAmms({ ordering: 'effective_end_date', page_size: 100 });

  if (analytics.isPending) return <LoadingBlock />;
  if (analytics.isError) return <ErrorBlock error={analytics.error} onRetry={() => analytics.refetch()} />;
  const { rows, total } = analytics.data;

  const chartData = rows.map((r) => ({
    name: r.country_iso2,
    [t('status.VALIDE')]: r.valid,
    [t('status.EXPIRE')]: r.expired,
    [t('status.IN_PROCESS')]: r.in_process,
    [t('status.INDETERMINE')]: r.undetermined,
  }));

  const topPriorities = [...(priorities.data?.results ?? [])]
    .filter((a) => a.urgency !== 'OK')
    .sort(
      (a, b) =>
        URGENCY_ORDER.indexOf(a.urgency) - URGENCY_ORDER.indexOf(b.urgency) ||
        (a.effective_end_date ?? '').localeCompare(b.effective_end_date ?? ''),
    )
    .slice(0, 10);

  return (
    <Box>
      <PageHeader title={t('dashboard.title')} subtitle={t('dashboard.subtitle')} />
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: t('dashboard.kpi.total'), value: total.total, color: '#0f5c8c' },
          {
            label: t('dashboard.kpi.valid'),
            value: `${total.valid} (${pct(total.pct_valid)})`,
            color: STATUS_COLORS.VALIDE,
          },
          { label: t('dashboard.kpi.expired'), value: total.expired, color: STATUS_COLORS.EXPIRE },
          { label: t('dashboard.kpi.inProcess'), value: total.in_process, color: STATUS_COLORS.IN_PROCESS },
          {
            label: t('dashboard.kpi.undetermined'),
            value: total.undetermined,
            color: STATUS_COLORS.INDETERMINE,
          },
          { label: t('dashboard.kpi.expiring6m'), value: total.expiring_6m, color: '#ef6c00' },
          { label: t('dashboard.kpi.expiring12m'), value: total.expiring_12m, color: '#1565c0' },
          { label: t('dashboard.kpi.pctComplete'), value: pct(total.pct_complete), color: '#00897b' },
        ].map((k) => (
          <Grid key={k.label} size={{ xs: 6, sm: 4, md: 3, lg: 1.5 }}>
            <KpiCard label={k.label} value={k.value} color={k.color} />
          </Grid>
        ))}
      </Grid>

      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardHeader title={t('dashboard.table.title')} titleTypographyProps={{ variant: 'h6' }} />
        <CardContent sx={{ pt: 0 }}>
          <AfricaTable rows={rows} total={total} />
        </CardContent>
      </Card>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 6 }}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardHeader title={t('dashboard.chart.title')} titleTypographyProps={{ variant: 'h6' }} />
            <CardContent sx={{ height: 360 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey={t('status.VALIDE')} stackId="a" fill={STATUS_COLORS.VALIDE} />
                  <Bar dataKey={t('status.IN_PROCESS')} stackId="a" fill={STATUS_COLORS.IN_PROCESS} />
                  <Bar dataKey={t('status.EXPIRE')} stackId="a" fill={STATUS_COLORS.EXPIRE} />
                  <Bar dataKey={t('status.INDETERMINE')} stackId="a" fill={STATUS_COLORS.INDETERMINE} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 6 }}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardHeader title={t('dashboard.priorities')} titleTypographyProps={{ variant: 'h6' }} />
            <CardContent sx={{ pt: 0 }}>
              {topPriorities.length === 0 ? (
                <Typography color="text.secondary">{t('dashboard.prioritiesEmpty')}</Typography>
              ) : (
                <PrioritiesTable amms={topPriorities} showCountry />
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
