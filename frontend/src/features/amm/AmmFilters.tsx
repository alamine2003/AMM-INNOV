import { Box, FormControl, InputLabel, MenuItem, Select, TextField } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { AmmFilters as Filters } from '@/api/types';
import { useCountries, useRanges } from '@/api/hooks/useCatalog';
import { AMM_STATUSES, DOSSIER_STATES, URGENCIES } from '@/lib/urgency';
import { useAuthStore } from '@/features/auth/authStore';

export function AmmFilters({ value, onChange }: { value: Filters; onChange: (next: Filters) => void }) {
  const { t } = useTranslation();
  const countries = useCountries();
  const ranges = useRanges();
  const user = useAuthStore((s) => s.user);
  const visibleCountries = (countries.data ?? []).filter(
    (c) => user?.role !== 'COUNTRY_REGULATORY' || user.countries.includes(c.iso2),
  );
  const set = (patch: Partial<Filters>) => onChange({ ...value, ...patch, page: 1 });

  const select = (
    label: string,
    key: keyof Filters,
    options: { value: string; label: string }[],
    testId: string,
  ) => (
    <FormControl size="small" sx={{ minWidth: 160 }}>
      <InputLabel id={`filter-${key}`}>{label}</InputLabel>
      <Select
        labelId={`filter-${key}`}
        label={label}
        value={(value[key] as string) ?? ''}
        onChange={(e) => set({ [key]: e.target.value } as Partial<Filters>)}
        inputProps={{ 'data-testid': testId }}
      >
        <MenuItem value="">{t('app.all')}</MenuItem>
        {options.map((o) => (
          <MenuItem key={o.value} value={o.value}>
            {o.label}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, mb: 2 }}>
      <TextField
        size="small"
        label={t('app.search')}
        placeholder={t('amm.filters.search')}
        value={value.search ?? ''}
        onChange={(e) => set({ search: e.target.value })}
        sx={{ minWidth: 220 }}
        inputProps={{ 'data-testid': 'filter-search' }}
      />
      {select(
        t('amm.filters.country'),
        'country',
        visibleCountries.map((c) => ({ value: c.iso2, label: c.name })),
        'filter-country',
      )}
      {select(
        t('amm.filters.range'),
        'range',
        (ranges.data ?? []).map((r) => ({ value: r.code, label: r.label })),
        'filter-range',
      )}
      {select(
        t('amm.filters.status'),
        'status',
        AMM_STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) })),
        'filter-status',
      )}
      {select(
        t('amm.filters.urgency'),
        'urgency',
        URGENCIES.map((u) => ({ value: u, label: t(`urgency.${u}`) })),
        'filter-urgency',
      )}
      {select(
        t('amm.filters.dossier'),
        'dossier_state',
        DOSSIER_STATES.map((d) => ({ value: d, label: t(`dossier.${d}`) })),
        'filter-dossier',
      )}
      {select(
        t('amm.filters.scan'),
        'has_current_scan',
        [
          { value: 'false', label: t('amm.filters.scanMissing') },
          { value: 'true', label: t('amm.filters.scanPresent') },
        ],
        'filter-scan',
      )}
      <TextField
        size="small"
        type="date"
        label={t('amm.filters.expiresBefore')}
        value={value.expires_before ?? ''}
        onChange={(e) => set({ expires_before: e.target.value })}
        slotProps={{ inputLabel: { shrink: true } }}
      />
    </Box>
  );
}
