import type { BinderField, BinderPage, BinderSlot } from '@/api/types';
import { formatDate } from '@/lib/dates';

/** Champs d'une page du classeur (blocs AMM d'origine et dernier renouvellement). */

export const FIELDS: { field: BinderField; label: string }[] = [
  { field: 'number', label: "N° d'AMM" },
  { field: 'start_date', label: 'Date de début' },
  { field: 'end_date', label: 'Date de fin' },
];
export const SLOTS: { slot: BinderSlot; title: string }[] = [
  { slot: 'original', title: "AMM d'origine" },
  { slot: 'renewal', title: 'Dernier renouvellement' },
];

export type Values = Record<string, string>;
export const id = (slot: BinderSlot, field: BinderField) => `${slot}.${field}`;

export function initialValues(page: BinderPage): Values {
  const values: Values = {};
  for (const { slot } of SLOTS) {
    const source = slot === 'original' ? page.original : page.renewal;
    for (const { field } of FIELDS) values[id(slot, field)] = (source?.[field] as string | null) ?? '';
  }
  return values;
}

export function show(field: BinderField, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  return field === 'number' ? String(value) : formatDate(String(value));
}
