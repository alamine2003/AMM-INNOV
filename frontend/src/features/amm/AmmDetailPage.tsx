import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, Chip, Paper, Stack, Tab, Tabs, Typography } from '@mui/material';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useAmm } from '@/api/hooks/useAmms';
import { api } from '@/api/client';
import { PageHeader } from '@/components/PageHeader';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { DossierChip, StatusChip, UrgencyChip } from '@/components/chips';
import { formatDate, formatRemaining } from '@/lib/dates';
import { canEditCountry, useAuthStore } from '@/features/auth/authStore';
import { AmmDetailTab } from './AmmDetailTab';
import { AmmHistoryTab } from './AmmHistoryTab';
import { AmmAlertsTab } from './AmmAlertsTab';
import { RenewalsTab } from '@/features/renewals/RenewalsTab';
import { DocumentsTab } from '@/features/documents/DocumentsTab';
import type { Renewal } from '@/api/types';

const TABS = ['detail', 'renewals', 'documents', 'alerts', 'history'] as const;
type TabKey = (typeof TABS)[number];

export default function AmmDetailPage() {
  const params = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const resolvedId = params.id;

  // Route /renewals/:renewalId : on résout l'AMM parente puis on redirige vers l'onglet Renouvellements.
  const renewalQuery = useQuery({
    queryKey: ['renewals', 'detail', params.renewalId ?? ''],
    queryFn: async () => (await api.get<Renewal>(`/renewals/${params.renewalId}`)).data,
    enabled: !resolvedId && !!params.renewalId,
  });
  useEffect(() => {
    if (renewalQuery.data) navigate(`/amms/${renewalQuery.data.amm}?tab=renewals`, { replace: true });
  }, [renewalQuery.data, navigate]);

  const amm = useAmm(resolvedId);
  const user = useAuthStore((s) => s.user);
  const tabParam = searchParams.get('tab') as TabKey | null;
  const tab: TabKey = tabParam && TABS.includes(tabParam) ? tabParam : 'detail';
  const setTab = (next: TabKey) => {
    const sp = new URLSearchParams(searchParams);
    sp.set('tab', next);
    setSearchParams(sp, { replace: true });
  };

  if (!resolvedId) return renewalQuery.isError ? <ErrorBlock error={renewalQuery.error} /> : <LoadingBlock />;
  if (amm.isPending) return <LoadingBlock />;
  if (amm.isError) return <ErrorBlock error={amm.error} onRetry={() => amm.refetch()} />;
  const data = amm.data;
  const editable = canEditCountry(user, data.country_iso2);

  return (
    <Box>
      <PageHeader
        title={data.product_name}
        subtitle={
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
            <Chip size="small" label={`${data.country_name} (${data.country_iso2})`} />
            <Chip size="small" label={data.range_code} variant="outlined" />
            <StatusChip value={data.status} />
            <UrgencyChip value={data.urgency} />
            <DossierChip value={data.dossier_state} />
            <Typography variant="body2" color="text.secondary">
              {t('amm.fields.effectiveEnd')} : {formatDate(data.effective_end_date)} (
              {formatRemaining(data.effective_end_date)})
            </Typography>
          </Stack>
        }
      />
      {!editable && (
        <Typography variant="body2" color="warning.main" sx={{ mb: 1 }}>
          {t('amm.readOnly')}
        </Typography>
      )}
      <Paper variant="outlined">
        <Tabs
          value={tab}
          onChange={(_e, v: TabKey) => setTab(v)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          {TABS.map((k) => (
            <Tab key={k} value={k} label={t(`amm.tabs.${k}`)} data-testid={`tab-${k}`} />
          ))}
        </Tabs>
        <Box sx={{ p: { xs: 2, md: 3 } }}>
          {tab === 'detail' && <AmmDetailTab amm={data} editable={editable} />}
          {tab === 'renewals' && <RenewalsTab amm={data} editable={editable} />}
          {tab === 'documents' && <DocumentsTab amm={data} editable={editable} />}
          {tab === 'alerts' && <AmmAlertsTab ammId={data.id} />}
          {tab === 'history' && <AmmHistoryTab ammId={data.id} />}
        </Box>
      </Paper>
    </Box>
  );
}
