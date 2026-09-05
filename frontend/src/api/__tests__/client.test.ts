import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { api } from '@/api/client';
import { db } from '@/mocks/handlers';
import { server } from '@/mocks/server';
import { useAuthStore } from '@/features/auth/authStore';

describe('client axios — refresh sur 401', () => {
  it('rafraîchit le jeton une fois (cookie de session) et rejoue la requête', async () => {
    db.session = 'u-hq';
    useAuthStore.getState().setSession({ access: 'mock-access-expired', user: null });
    let refreshCalls = 0;
    server.use(
      http.post('/api/v1/auth/refresh', async () => {
        refreshCalls += 1;
        return HttpResponse.json({ access: 'mock-access-u-hq' });
      }),
    );
    const res = await api.get('/me');
    expect(res.status).toBe(200);
    expect(res.data.email).toBe('siege@amm-innov.test');
    expect(refreshCalls).toBe(1);
    expect(useAuthStore.getState().access).toBe('mock-access-u-hq');
  });

  it('déconnecte si le refresh échoue (cookie absent ou révoqué)', async () => {
    db.session = null;
    useAuthStore.getState().setSession({ access: 'mock-access-expired', user: null });
    await expect(api.get('/me')).rejects.toBeTruthy();
    expect(useAuthStore.getState().access).toBeNull();
    expect(useAuthStore.getState().sessionChecked).toBe(true);
  });

  it('envoie le Bearer sur chaque requête authentifiée', async () => {
    useAuthStore.getState().setSession({ access: 'mock-access-u-sn', user: null });
    const res = await api.get('/me');
    expect(res.data.role).toBe('COUNTRY_REGULATORY');
  });
});
