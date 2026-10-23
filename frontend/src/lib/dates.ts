import {
  addYears,
  differenceInCalendarDays,
  differenceInMonths,
  format,
  isValid,
  parse,
  parseISO,
  startOfDay,
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

/** Mois entiers restants (le 23/10 → le 13/03 dans 2 ans et 4 mois = 28, pas 29). */
export function monthsUntil(value: string | null | undefined, today = new Date()): number | null {
  const d = parseApiDate(value);
  if (!d) return null;
  return differenceInMonths(d, startOfDay(today));
}

/** 28 → « 2 ans et 4 mois », 12 → « 1 an », 4 → « 4 mois ». */
export function formatMonthsSpan(totalMonths: number): string {
  const months = Math.abs(totalMonths);
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const y = years ? `${years} an${years > 1 ? 's' : ''}` : '';
  const m = rest ? `${rest} mois` : '';
  return y && m ? `${y} et ${m}` : y || m || '0 mois';
}

/** « 45 j (1 mois) », « 872 j (2 ans et 4 mois) », « −12 j » … */
export function formatRemaining(value: string | null | undefined, today = new Date()): string {
  const days = daysUntil(value, today);
  if (days === null) return '—';
  const sign = days < 0 ? '−' : '';
  const d = parseApiDate(value) as Date;
  const t = startOfDay(today);
  const months = days < 0 ? differenceInMonths(t, d) : differenceInMonths(d, t);
  return `${sign}${Math.abs(days)} j${months >= 1 ? ` (${sign}${formatMonthsSpan(months)})` : ''}`;
}

/** Fin de validité calculée : début + durée de validité du pays (5 ans en général). */
export function addValidity(start: string | null | undefined, years: number): string | null {
  const d = parseApiDate(start);
  return d ? toApiDate(addYears(d, years)) : null;
}

/** Durée entre deux dates, en années et mois entiers : « 5 ans », « 4 ans et 11 mois ». */
export function formatSpan(start: string | null | undefined, end: string | null | undefined): string | null {
  const a = parseApiDate(start);
  const b = parseApiDate(end);
  if (!a || !b) return null;
  const months = differenceInMonths(b, a);
  if (months < 0) return null;
  if (months === 0) return `${differenceInCalendarDays(b, a)} j`;
  return formatMonthsSpan(months);
}

/** « 2026-09 » → « sept. 2026 ». */
export function formatMonth(yyyyMm: string): string {
  const d = parse(yyyyMm, 'yyyy-MM', new Date());
  return isValid(d) ? format(d, 'MMM yyyy', { locale: fr }) : yyyyMm;
}

export const todayIso = () => toApiDate(new Date());
