import type { useChronologyEdits } from '@/api/hooks/useBinders';
import { type ChronologyPeriod } from '@/api/hooks/useBinders';
import type {
  BinderChronologyDocument,
  BinderChronologyEntry,
  BinderDocumentKind,
  BinderPage,
} from '@/api/types';
import { formatDate } from '@/lib/dates';
import i18n from '@/lib/i18n';
import { type usePageScanImport } from './PageScanImport';

/** Chronologie d'une page : couleurs, types d'édition et petits calculs partagés. */

export type ScanImport = ReturnType<typeof usePageScanImport>;
export type Edits = ReturnType<typeof useChronologyEdits>;

export const KIND_COLORS: Record<BinderChronologyEntry['kind'], string> = {
  pending: '#ef6c00',
  renewal: '#1565c0',
  origin: '#2e7d32',
  closed: '#757575',
  gap: '#c62828',
};

/** `labelKey` : clé de traduction du libellé (résolue au rendu, pour suivre la langue). */
export const DOCUMENT_KINDS: { value: BinderDocumentKind; labelKey: string }[] = [
  { value: 'AMM', labelKey: 'binders.chronology.kindDecision' },
  { value: 'RECEPISSE', labelKey: 'documentKind.RECEPISSE' },
  { value: 'COURRIER', labelKey: 'documentKind.COURRIER' },
  { value: 'AUTRE', labelKey: 'documentKind.AUTRE' },
];

/** Ce qui est ouvert en édition dans la chronologie : une seule chose à la fois. */
export type Editing =
  | { type: 'period'; period: ChronologyPeriod }
  | { type: 'cancel'; period: string }
  | { type: 'add'; period: ChronologyPeriod }
  | { type: 'document'; period: ChronologyPeriod; doc: BinderChronologyDocument }
  | null;

/** Nombre de manques sur la page (décisions non scannées, dates, trous de validité…). */
export function chronologyIssues(page: Pick<BinderPage, 'chronology'>): number {
  return page.chronology.reduce((total, entry) => total + entry.issues.length, 0);
}

export function period(entry: BinderChronologyEntry): string {
  if (entry.kind === 'pending') {
    return entry.filing_date
      ? i18n.t('binders.chronology.filedOn', { date: formatDate(entry.filing_date) })
      : i18n.t('binders.chronology.undatedFiling');
  }
  if (!entry.start_date && !entry.end_date) return i18n.t('binders.chronology.datesUnknown');
  return i18n.t('binders.chronology.fromTo', {
    start: entry.start_date ? formatDate(entry.start_date) : '?',
    end: entry.end_date ? formatDate(entry.end_date) : '?',
  });
}

export const periodOf = (entry: BinderChronologyEntry): ChronologyPeriod => entry.renewal_id ?? 'origin';
