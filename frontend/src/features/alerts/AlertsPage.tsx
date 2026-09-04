import {
  Box,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  TablePagination,
} from '@mui/material';
import { useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useAlerts } from '@/api/hooks/useAlerts';
import { useCountries } from '@/api/hooks/useCatalog';
import type { AlertFilters } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { useAuthStore } from '@/features/auth/authStore';
import { AlertsTable } from './AlertsTable';

export default function AlertsPage() {
  const { t } = useTranslation();
  const [sp, setSp] = useSearchParams();
  const user = useAuthStore((s) => s.user);
  const countries = useCountries();
  const filters: AlertFilters = {
    status: (sp.get('status') as AlertFilters['status']) ?? 'OPEN',
    country: sp.get('country') ?? '',
    severity: (sp.get('severity') as AlertFilters['severity']) ?? '',
    assigned_to: sp.get('assigned_to') === 'me' ? 'me' : '',
    page: Number(sp.get('page') ?? 1),
    page_size: 25,
  };
  const set = (patch: Partial<AlertFilters>) => {
    const next = new URLSearchParams();
    const merged = { ...filters, ...patch, page: patch.page ?? 1 };
    for (const [k, v] of Object.entries(merged))
      if (v !== '' && v !== undefined && k !== 'page_size') next.set(k, String(v));
    setSp(next);
  };
  const alerts = useAlerts(filters);
  const visibleCountries = (countries.data ?? []).filter(
    (c) => user?.role !== 'COUNTRY_REGULATORY' || user.countries.includes(c.iso2),
  );

  return (
    <Box>
      <PageHeader title={t('alerts.title')} />
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center" sx={{ mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="al-status">{t('alerts.filters.status')}</InputLabel>
          <Select
            labelId="al-status"
            label={t('alerts.filters.status')}
            value={filters.status ?? ''}
            onChange={(e) => set({ status: e.target.value as AlertFilters['status'] })}
            inputProps={{ 'data-testid': 'alert-filter-status' }}
          >
            <MenuItem value="">{t('app.all')}</MenuItem>
            {(['OPEN', 'ACKNOWLEDGED', 'RESOLVED'] as const).map((s) => (
              <MenuItem key={s} value={s}>
                {t(`alertStatus.${s}`)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="al-country">{t('alerts.filters.country')}</InputLabel>
          <Select
            labelId="al-country"
            label={t('alerts.filters.country')}
            value={filters.country ?? ''}
            onChange={(e) => set({ country: e.target.value })}
          >
            <MenuItem value="">{t('app.all')}</MenuItem>
            {visibleCountries.map((c) => (
              <MenuItem key={c.iso2} value={c.iso2}>
                {c.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="al-sev">{t('alerts.filters.severity')}</InputLabel>
          <Select
            labelId="al-sev"
            label={t('alerts.filters.severity')}
            value={filters.severity ?? ''}
            onChange={(e) => set({ severity: e.target.value as AlertFilters['severity'] })}
          >
            <MenuItem value="">{t('app.all')}</MenuItem>
            {(['INFO', 'WARNING', 'CRITICAL'] as const).map((s) => (
              <MenuItem key={s} value={s}>
                {t(`severity.${s}`)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControlLabel
          control={
            <Switch
              checked={filters.assigned_to === 'me'}
              onChange={(e) => set({ assigned_to: e.target.checked ? 'me' : '' })}
            />
          }
          label={t('alerts.mine')}
        />
      </Stack>
      <Paper variant="outlined">
        {alerts.isPending && <LoadingBlock />}
        {alerts.isError && <ErrorBlock error={alerts.error} onRetry={() => alerts.refetch()} />}
        {alerts.data && alerts.data.results.length === 0 && <EmptyBlock text={t('alerts.empty')} />}
        {alerts.data && alerts.data.results.length > 0 && (
          <>
            <AlertsTable alerts={alerts.data.results} />
            <TablePagination
              component="div"
              count={alerts.data.count}
              page={(filters.page ?? 1) - 1}
              rowsPerPage={25}
              rowsPerPageOptions={[25]}
              onPageChange={(_e, p) => set({ page: p + 1 })}
            />
          </>
        )}
      </Paper>
    </Box>
  );
}
