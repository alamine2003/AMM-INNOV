import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSnackbar } from 'notistack';
import { useTranslation } from 'react-i18next';
import { queryKeys } from '@/api/queryKeys';
import type { RealtimeEvent } from '@/api/types';
import { useAuthStore } from '@/features/auth/authStore';
import { keysToInvalidate } from './invalidation';
import { useRealtimeStore } from './realtimeStore';

const MIN_DELAY = 1000;
const MAX_DELAY = 30000;
const POLL_INTERVAL = 60000;
/** Au-delà de ce nombre d'échecs consécutifs, on passe en mode polling (tout en continuant de tenter la reconnexion). */
const POLLING_AFTER_FAILURES = 3;

/** Sous-protocole WebSocket portant le jeton d'accès (jamais dans l'URL : les proxys journalisent les query strings). */
export const WS_SUBPROTOCOL = 'amm.jwt';

export function buildWsUrl(): string {
  const configured = import.meta.env.VITE_WS_URL as string | undefined;
  if (configured) return configured;
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/`;
}

/**
 * Connexion WebSocket unique, reconnexion exponentielle 1 s → 30 s, repli en polling 60 s.
 * À monter une seule fois dans le layout authentifié.
 */
export function useRealtime(enabled = true) {
  const qc = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();
  const { t } = useTranslation();
  const access = useAuthStore((s) => s.access);
  const setStatus = useRealtimeStore((s) => s.setStatus);
  const touch = useRealtimeStore((s) => s.touch);
  const status = useRealtimeStore((s) => s.status);

  const socketRef = useRef<WebSocket | null>(null);
  const failuresRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByUsRef = useRef(false);

  useEffect(() => {
    if (!enabled || !access || typeof WebSocket === 'undefined' || import.meta.env.VITE_USE_MOCKS === '1') {
      setStatus(enabled && access ? 'polling' : 'idle');
      return;
    }
    closedByUsRef.current = false;

    const clearTimer = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
    };

    const handleEvent = (event: RealtimeEvent) => {
      touch();
      for (const key of keysToInvalidate(event)) {
        void qc.invalidateQueries({ queryKey: key });
      }
      if (event.type === 'notification.created') {
        enqueueSnackbar(event.title ?? t('notifications.new'), { variant: 'info' });
        void qc.invalidateQueries({ queryKey: queryKeys.notifications.unreadCount() });
      }
    };

    const connect = () => {
      const token = useAuthStore.getState().access;
      if (!token || closedByUsRef.current) return;
      let ws: WebSocket;
      try {
        ws = new WebSocket(buildWsUrl(), [WS_SUBPROTOCOL, token]);
      } catch {
        scheduleReconnect();
        return;
      }
      socketRef.current = ws;
      ws.onopen = () => {
        failuresRef.current = 0;
        setStatus('connected');
      };
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(String(msg.data)) as RealtimeEvent;
          if (data && typeof data.type === 'string') handleEvent(data);
        } catch {
          /* message ignoré */
        }
      };
      ws.onerror = () => {
        /* onclose suit toujours */
      };
      ws.onclose = () => {
        socketRef.current = null;
        if (closedByUsRef.current) return;
        scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      failuresRef.current += 1;
      const delay = Math.min(MAX_DELAY, MIN_DELAY * 2 ** (failuresRef.current - 1));
      setStatus(failuresRef.current >= POLLING_AFTER_FAILURES ? 'polling' : 'reconnecting');
      clearTimer();
      timerRef.current = setTimeout(connect, delay);
    };

    connect();

    return () => {
      closedByUsRef.current = true;
      clearTimer();
      socketRef.current?.close();
      socketRef.current = null;
      setStatus('idle');
    };
  }, [enabled, access, qc, enqueueSnackbar, t, setStatus, touch]);

  // Repli : polling toutes les 60 s tant que le WebSocket n'est pas connecté.
  useEffect(() => {
    if (!enabled || !access || status === 'connected') return;
    const id = setInterval(() => {
      void qc.invalidateQueries({ queryKey: queryKeys.amms.all });
      void qc.invalidateQueries({ queryKey: queryKeys.alerts.all });
      void qc.invalidateQueries({ queryKey: queryKeys.analytics.all });
      void qc.invalidateQueries({ queryKey: queryKeys.notifications.all });
    }, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [enabled, access, status, qc]);

  return status;
}
