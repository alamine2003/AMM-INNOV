import type { QueryKey } from '@tanstack/react-query';
import { queryKeys } from '@/api/queryKeys';
import type { RealtimeEvent, RealtimeEventType } from '@/api/types';

/**
 * Table événement → clés de requêtes à invalider.
 * Les événements ne transportent que des identifiants : les données sont rechargées via l'API.
 */
export function keysToInvalidate(event: RealtimeEvent): QueryKey[] {
  const { type, id, country, amm } = event;
  const ammId = amm ?? id;
  const table: Record<RealtimeEventType, () => QueryKey[]> = {
    'amm.created': () => [
      queryKeys.amms.all,
      queryKeys.analytics.all,
      ...(country ? [queryKeys.countries.documents(country)] : []),
    ],
    'amm.updated': () => [
      ...(id ? [queryKeys.amms.detail(id), queryKeys.amms.history(id)] : []),
      queryKeys.amms.list(),
      queryKeys.analytics.all,
    ],
    'renewal.transitioned': () => [
      ...(ammId
        ? [queryKeys.amms.renewals(ammId), queryKeys.amms.detail(ammId), queryKeys.amms.history(ammId)]
        : []),
      queryKeys.amms.list(),
      queryKeys.alerts.all,
      queryKeys.analytics.all,
    ],
    'alert.created': () => [queryKeys.alerts.all, ...(ammId ? [queryKeys.amms.alerts(ammId)] : [])],
    'alert.updated': () => [queryKeys.alerts.all, ...(ammId ? [queryKeys.amms.alerts(ammId)] : [])],
    'notification.created': () => [queryKeys.notifications.all],
    'document.created': () => [
      ...(ammId
        ? [queryKeys.amms.documents(ammId, true), queryKeys.amms.detail(ammId), queryKeys.amms.history(ammId)]
        : []),
      queryKeys.amms.list(),
      queryKeys.documents.all,
      ...(country ? [queryKeys.countries.documents(country)] : [queryKeys.countries.all]),
      queryKeys.products.all,
    ],
    'dashboard.refresh': () => [queryKeys.analytics.all, queryKeys.amms.list()],
  };
  const resolver = table[type];
  return resolver ? resolver() : [];
}

export const KNOWN_EVENTS: RealtimeEventType[] = [
  'amm.updated',
  'amm.created',
  'renewal.transitioned',
  'alert.created',
  'alert.updated',
  'notification.created',
  'document.created',
  'dashboard.refresh',
];
