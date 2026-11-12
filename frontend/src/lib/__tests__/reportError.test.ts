import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it } from 'vitest';
import { useAuthStore } from '@/features/auth/authStore';
import { reportError, resetReportedErrors } from '@/lib/reportError';
import { server } from '@/mocks/server';

describe('erreurs de l’interface envoyées au journal', () => {
  afterEach(() => {
    resetReportedErrors();
    useAuthStore.getState().logout();
  });

  it('envoie une erreur une seule fois, et seulement connecté', async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post('/api/v1/client-errors', async ({ request }) => {
        bodies.push(await request.json());
        return new HttpResponse(null, { status: 204 });
      }),
    );
    expect(reportError(new TypeError('x is undefined'), '/amms')).toBe(false); // pas connecté
    useAuthStore.getState().setSession({ access: 'jeton' });
    expect(reportError(new TypeError('x is undefined'), '/amms')).toBe(true);
    expect(reportError(new TypeError('x is undefined'), '/amms')).toBe(false); // déjà envoyée
    expect(reportError(new TypeError("'text/html' is not a valid JavaScript MIME type"))).toBe(false);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(bodies).toEqual([
      expect.objectContaining({ kind: 'TypeError', message: 'x is undefined', path: '/amms' }),
    ]);
  });
});
