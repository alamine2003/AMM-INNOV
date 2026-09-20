/**
 * Sentry côté navigateur : erreurs de l'interface, actif seulement si VITE_SENTRY_DSN est fourni.
 *
 * Application réglementaire : aucune capture d'écran ni rejeu de session, et les adresses IP ne
 * sont pas envoyées (`sendDefaultPii: false`). On remonte l'erreur et sa pile, pas l'utilisateur.
 */
import * as Sentry from '@sentry/react';

export type SentryOptions = {
  dsn: string;
  environment: string;
  release?: string;
  tracesSampleRate: number;
  sendDefaultPii: false;
};

/** Options d'initialisation, ou null quand aucun DSN n'est configuré. */
export function sentryOptions(env: ImportMetaEnv): SentryOptions | null {
  const dsn = env.VITE_SENTRY_DSN?.trim();
  if (!dsn) return null;
  const rate = Number(env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? '0');
  return {
    dsn,
    environment: env.VITE_SENTRY_ENVIRONMENT?.trim() || 'production',
    release: env.VITE_SENTRY_RELEASE?.trim() || undefined,
    tracesSampleRate: Number.isFinite(rate) ? rate : 0,
    sendDefaultPii: false,
  };
}

/** Initialise Sentry au démarrage. Retourne true quand la surveillance est active. */
export function initSentry(env: ImportMetaEnv = import.meta.env): boolean {
  const options = sentryOptions(env);
  if (!options) return false;
  Sentry.init(options);
  return true;
}
