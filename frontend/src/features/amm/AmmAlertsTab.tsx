import { useAmmAlerts } from '@/api/hooks/useAmms';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { AlertsTable } from '@/features/alerts/AlertsTable';
import { useTranslation } from 'react-i18next';

export function AmmAlertsTab({ ammId }: { ammId: string }) {
  const { t } = useTranslation();
  const alerts = useAmmAlerts(ammId);
  if (alerts.isPending) return <LoadingBlock />;
  if (alerts.isError) return <ErrorBlock error={alerts.error} onRetry={() => alerts.refetch()} />;
  if (alerts.data.length === 0) return <EmptyBlock text={t('alerts.empty')} />;
  return <AlertsTable alerts={alerts.data} hideAmm />;
}
