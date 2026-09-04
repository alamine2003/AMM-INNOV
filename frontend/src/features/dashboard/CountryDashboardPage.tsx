import { Box, Button, Card, CardContent, CardHeader, Grid2 as Grid, Typography } from '@mui/material';
import { Link, useParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useCountryAnalytics } from '@/api/hooks/useAnalytics';
import { useCountries } from '@/api/hooks/useCatalog';
import { PageHeader } from '@/components/PageHeader';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { AMM_STATUSES, STATUS_COLORS } from '@/lib/urgency';
import { formatMonth } from '@/lib/dates';
import { PrioritiesTable } from './PrioritiesTable';

export default function CountryDashboardPage() {
  const { iso2 = '' } = useParams();
  const { t } = useTranslation();
  const countries = useCountries();
  const analytics = useCountryAnalytics(iso2);
  const country = countries.data?.find((c) => c.iso2 === iso2);

  if (analytics.isPending) return <LoadingBlock />;
  if (analytics.isError) return <ErrorBlock error={analytics.error} onRetry={() => analytics.refetch()} />;

  const rangeMap = new Map<string, Record<string, number | string>>();
  for (const row of analytics.data.by_range_status) {
    const entry = rangeMap.get(row.range) ?? { name: row.range };
    entry[t(`status.${row.status}`)] = Number(entry[t(`status.${row.status}`)] ?? 0) + row.count;
    rangeMap.set(row.range, entry);
  }
  const pipeline = analytics.data.pipeline.map((p) => ({ ...p, label: formatMonth(p.month) }));

  return (
    <Box>
      <PageHeader
        title={t('dashboard.countryTitle', { name: country?.name ?? iso2 })}
        subtitle={
          country
            ? `${country.authority} — ${t('admin.countries.validity')} : ${country.validity_years}, ${t('admin.countries.lead')} : ${country.filing_lead_months}`
            : undefined
        }
        actions={
          <Button component={Link} to={`/amms?country=${iso2}`} variant="outlined">
            {t('dashboard.viewAmms')}
          </Button>
        }
      />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardHeader title={t('dashboard.byRangeStatus')} titleTypographyProps={{ variant: 'h6' }} />
            <CardContent sx={{ height: 320 }}>
              {rangeMap.size === 0 ? (
                <EmptyBlock />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={Array.from(rangeMap.values())}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    {AMM_STATUSES.map((s) => (
                      <Bar key={s} dataKey={t(`status.${s}`)} stackId="a" fill={STATUS_COLORS[s]} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardHeader title={t('dashboard.pipeline')} titleTypographyProps={{ variant: 'h6' }} />
            <CardContent sx={{ height: 320 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pipeline}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" interval={2} angle={-30} textAnchor="end" height={60} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" name={t('nav.amms')} fill="#ef6c00" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={12}>
          <Card variant="outlined">
            <CardHeader title={t('dashboard.urgencies')} titleTypographyProps={{ variant: 'h6' }} />
            <CardContent sx={{ pt: 0 }}>
              {analytics.data.priorities.length === 0 ? (
                <Typography color="text.secondary">{t('dashboard.prioritiesEmpty')}</Typography>
              ) : (
                <PrioritiesTable amms={analytics.data.priorities} />
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
