import { describe, expect, it } from 'vitest';
import { keysToInvalidate, KNOWN_EVENTS } from '@/realtime/invalidation';
import { queryKeys } from '@/api/queryKeys';

describe('table d’invalidation temps réel', () => {
  it('amm.updated invalide la fiche, l’historique, la liste et les analytics', () => {
    const keys = keysToInvalidate({ type: 'amm.updated', id: 'amm-1', country: 'SN' });
    expect(keys).toContainEqual(queryKeys.amms.detail('amm-1'));
    expect(keys).toContainEqual(queryKeys.amms.history('amm-1'));
    expect(keys).toContainEqual(queryKeys.amms.list());
    expect(keys).toContainEqual(queryKeys.analytics.all);
  });
  it('renewal.transitioned invalide renouvellements, alertes et analytics', () => {
    const keys = keysToInvalidate({ type: 'renewal.transitioned', id: 'ren-1', amm: 'amm-1' });
    expect(keys).toContainEqual(queryKeys.amms.renewals('amm-1'));
    expect(keys).toContainEqual(queryKeys.alerts.all);
    expect(keys).toContainEqual(queryKeys.analytics.all);
  });
  it('document.created invalide le dossier documentaire et la bibliothèque pays', () => {
    const keys = keysToInvalidate({ type: 'document.created', amm: 'amm-1', country: 'SN' });
    expect(keys).toContainEqual(queryKeys.amms.documents('amm-1', true));
    expect(keys).toContainEqual(queryKeys.countries.documents('SN'));
    expect(keys).toContainEqual(queryKeys.documents.all);
  });
  it('notification.created invalide les notifications ; dashboard.refresh les analytics', () => {
    expect(keysToInvalidate({ type: 'notification.created' })).toEqual([queryKeys.notifications.all]);
    expect(keysToInvalidate({ type: 'dashboard.refresh' })).toContainEqual(queryKeys.analytics.all);
  });
  it('couvre tous les événements connus et ignore les inconnus', () => {
    for (const type of KNOWN_EVENTS) expect(keysToInvalidate({ type, id: 'x' }).length).toBeGreaterThan(0);
    expect(keysToInvalidate({ type: 'inconnu' as never })).toEqual([]);
  });
});
