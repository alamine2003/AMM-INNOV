import {
  differenceInCalendarDays,
  differenceInCalendarMonths,
  format,
  isValid,
  parse,
  parseISO,
} from 'date-fns';
import { fr } from 'date-fns/locale';

export const DISPLAY_FORMAT = 'dd/MM/yyyy';

export function parseApiDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = parseISO(value);
  return isValid(d) ? d : null;
}

/** ISO 8601 (AAAA-MM-JJ ou datetime) → JJ/MM/AAAA. */
export function formatDate(value: string | Date | null | undefined, fallback = '—'): string {
  if (!value) return fallback;
  const d = value instanceof Date ? value : parseApiDate(value);
  if (!d) return fallback;
  return format(d, DISPLAY_FORMAT, { locale: fr });
}

export function formatDateTime(value: string | Date | null | undefined, fallback = '—'): string {
  if (!value) return fallback;
  const d = value instanceof Date ? value : parseApiDate(value);
  if (!d) return fallback;
  return format(d, 'dd/MM/yyyy HH:mm', { locale: fr });
}

/** JJ/MM/AAAA saisi par l'utilisateur → AAAA-MM-JJ ou null si invalide. */
export function parseDisplayDate(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const d = parse(trimmed, DISPLAY_FORMAT, new Date(), { locale: fr });
  return isValid(d) ? toApiDate(d) : null;
}

export function toApiDate(d: Date): string {
  return format(d, 'yyyy-MM-dd');
}

export function daysUntil(value: string | null | undefined, today = new Date()): number | null {
  const d = parseApiDate(value);
  if (!d) return null;
  return differenceInCalendarDays(d, today);
}

export function monthsUntil(value: string | null | undefined, today = new Date()): number | null {
  const d = parseApiDate(value);
  if (!d) return null;
  return differenceInCalendarMonths(d, today);
}

/** « 45 j (1 mois) », « −12 j » … */
export function formatRemaining(value: string | null | undefined, today = new Date()): string {
  const days = daysUntil(value, today);
  if (days === null) return '—';
  const months = monthsUntil(value, today) ?? 0;
  const sign = days < 0 ? '−' : '';
  const absDays = Math.abs(days);
  const absMonths = Math.abs(months);
  return `${sign}${absDays} j${absMonths >= 1 ? ` (${sign}${absMonths} mois)` : ''}`;
}

/** « 2026-09 » → « sept. 2026 ». */
export function formatMonth(yyyyMm: string): string {
  const d = parse(yyyyMm, 'yyyy-MM', new Date());
  return isValid(d) ? format(d, 'MMM yyyy', { locale: fr }) : yyyyMm;
}

export const todayIso = () => toApiDate(new Date());
