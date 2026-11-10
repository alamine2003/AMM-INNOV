import type { useChronologyEdits} from '@/api/hooks/useBinders';
import { type ChronologyPeriod } from '@/api/hooks/useBinders';
import type {
  BinderChronologyDocument,
  BinderChronologyEntry,
  BinderDocumentKind,
  BinderPage,
} from '@/api/types';
import { formatDate } from '@/lib/dates';
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

export const DOCUMENT_KINDS: { value: BinderDocumentKind; label: string }[] = [
  { value: 'AMM', label: 'Décision (AMM)' },
  { value: 'RECEPISSE', label: 'Récépissé de dépôt' },
  { value: 'COURRIER', label: "Courrier de l'autorité" },
  { value: 'AUTRE', label: 'Autre' },
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
    return entry.filing_date ? `déposé le ${formatDate(entry.filing_date)}` : 'dépôt non daté';
  }
  if (!entry.start_date && !entry.end_date) return 'dates inconnues';
  return `du ${entry.start_date ? formatDate(entry.start_date) : '?'} au ${
    entry.end_date ? formatDate(entry.end_date) : '?'
  }`;
}

export const periodOf = (entry: BinderChronologyEntry): ChronologyPeriod => entry.renewal_id ?? 'origin';
