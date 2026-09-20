import { describe, expect, it } from 'vitest';

import { sentryOptions } from '@/lib/sentry';

const env = (extra: Record<string, string>) => ({ ...extra }) as unknown as ImportMetaEnv;

describe('sentryOptions', () => {
  it('reste inactif sans DSN', () => {
    expect(sentryOptions(env({}))).toBeNull();
    expect(sentryOptions(env({ VITE_SENTRY_DSN: '   ' }))).toBeNull();
  });

  it("n'envoie aucune donnée personnelle et ne trace pas par défaut", () => {
    const options = sentryOptions(env({ VITE_SENTRY_DSN: 'https://clef@o0.ingest.sentry.io/1' }));
    expect(options).toMatchObject({
      environment: 'production',
      sendDefaultPii: false,
      tracesSampleRate: 0,
    });
    expect(options?.release).toBeUndefined();
  });

  it('reprend environnement, version et taux de traces fournis', () => {
    const options = sentryOptions(
      env({
        VITE_SENTRY_DSN: 'https://clef@o0.ingest.sentry.io/1',
        VITE_SENTRY_ENVIRONMENT: 'staging',
        VITE_SENTRY_RELEASE: '1.2.3',
        VITE_SENTRY_TRACES_SAMPLE_RATE: '0.1',
      }),
    );
    expect(options).toMatchObject({ environment: 'staging', release: '1.2.3', tracesSampleRate: 0.1 });
  });
});
