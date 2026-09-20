import { describe, expect, it } from 'vitest';
import { HEALTH_POLL_MS, HEALTH_TIMEOUT_MS, parseHealth, toApiHealthState } from '@/api/hooks/useHealth';
import type { Health } from '@/api/types';

describe('parseHealth', () => {
  it('accepte un corps 200 nominal', () => {
    expect(parseHealth({ status: 'ok', database: true, redis: true, version: '1.4.2' })).toEqual({
      status: 'ok',
      database: true,
      redis: true,
      version: '1.4.2',
    } satisfies Health);
  });

  it('accepte un corps 503 dégradé', () => {
    expect(parseHealth({ status: 'degraded', database: false, redis: true, version: '1.4.2' })).toEqual({
      status: 'degraded',
      database: false,
      redis: true,
      version: '1.4.2',
    } satisfies Health);
  });

  it('normalise une version absente en chaîne vide (déploiement décalé, ancien backend)', () => {
    expect(parseHealth({ status: 'ok', database: true, redis: true })).toEqual({
      status: 'ok',
      database: true,
      redis: true,
      version: '',
    } satisfies Health);
  });

  it.each<[string, unknown]>([
    ['une chaîne (page HTML)', '<html></html>'],
    ['un objet vide', {}],
    ['un statut hors contrat', { status: 'up', database: true, redis: true }],
    ['null', null],
  ])('rejette %s', (_label, body) => {
    expect(() => parseHealth(body)).toThrow('Réponse de santé non conforme');
  });
});

describe('toApiHealthState', () => {
  it('checking pendant la première sonde', () => {
    expect(toApiHealthState({ status: 'pending' })).toBe('checking');
  });

  it('online sur un 200 avec status "ok"', () => {
    const data: Health = { status: 'ok', database: true, redis: true, version: '1.4.2' };
    expect(toApiHealthState({ status: 'success', data })).toBe('online');
  });

  it('degraded sur un 503 avec status "degraded"', () => {
    const data: Health = { status: 'degraded', database: false, redis: true, version: '1.4.2' };
    expect(toApiHealthState({ status: 'success', data })).toBe('degraded');
  });

  it('unreachable sur une erreur (réseau, délai, code hors contrat)', () => {
    expect(toApiHealthState({ status: 'error' })).toBe('unreachable');
  });

  it('unreachable même quand des données antérieures sont conservées (jamais un "en ligne" périmé)', () => {
    const data: Health = { status: 'ok', database: true, redis: true, version: '1.4.2' };
    expect(toApiHealthState({ status: 'error', data })).toBe('unreachable');
  });
});

describe('constantes de polling', () => {
  it('sonde toutes les 60 s avec un délai de requête de 5 s', () => {
    expect(HEALTH_POLL_MS).toBe(60_000);
    expect(HEALTH_TIMEOUT_MS).toBe(5_000);
  });
});
