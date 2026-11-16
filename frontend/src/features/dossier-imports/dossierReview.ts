/**
 * Lecture « métier » d'un import de dossier : état du lot en une phrase, frise de l'AMM
 * (origine puis renouvellements) avec les scans rangés, sans clé technique ni arbitrage.
 */
import type { DossierImportBatch, DossierImportPreview, DossierImportTimelineStep } from '@/api/types';
import { formatDate } from '@/lib/dates';
import i18n from '@/lib/i18n';

/** Libellé d'un champ de la fiche (la clé technique si le champ est inconnu). */
export const fieldLabel = (field: string): string =>
  i18n.t(`dossierImports.fields.${field}`, { defaultValue: field });

/** Type d'une pièce du dossier (le code si le type est inconnu). */
export const documentKindLabel = (kind: string): string =>
  i18n.t(`dossierImports.documentKinds.${kind}`, { defaultValue: kind });

/** Valeur lisible d'un champ (dates au format français, états traduits). */
export function showValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return i18n.t('dossierImports.values.empty');
  if (field.endsWith('date')) return formatDate(String(value));
  if (field === 'workflow_status')
    return i18n.t(`workflow.${String(value)}`, { defaultValue: String(value) });
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}

type DossierDocument = DossierImportPreview['documents'][number];

const isoInKey = (key: string) => /(\d{4}-\d{2}-\d{2})/.exec(key)?.[1] ?? null;

/** « Renouvellement du 11/09/2018 », jamais la clé interne de la période. */
export function renewalTitle(
  renewal: { start_date: string | null; decision_date?: string | null } | null,
  key = '',
): string {
  const date = renewal?.start_date || renewal?.decision_date || isoInKey(key);
  if (date) return i18n.t('dossierImports.renewalTitle.onDate', { date: formatDate(date) });
  const year = /(?:^|\D)((?:19|20)\d{2})(?:\D|$)/.exec(key)?.[1];
  return year
    ? i18n.t('dossierImports.renewalTitle.ofYear', { year })
    : i18n.t('dossierImports.renewalTitle.unknown');
}

export function periodTitle(period: string, preview: DossierImportPreview): string {
  if (period === 'original') return i18n.t('dossierImports.period.original');
  if (period === 'unplaced') return i18n.t('dossierImports.period.unplaced');
  return renewalTitle(preview.renewals.find((renewal) => renewal.key === period) ?? null, period);
}

/** Retire les clés internes (« renewal-2026-01-01 ») d'un message du serveur. */
export function humanize(message: string, preview: DossierImportPreview): string {
  return message.replace(/renewal-[\w-]*\w/g, (key) => periodTitle(key, preview));
}

export interface TimelineStep {
  id: string;
  kind: 'original' | 'renewal';
  title: string;
  number: string;
  start: string | null;
  end: string | null;
  inForce: boolean;
  /** Étape créée par ce dossier (renouvellement obtenu lu sur une décision). */
  isNew: boolean;
  inDossier: boolean;
  scans: DossierDocument[];
}

const byStart = (a: { start: string | null }, b: { start: string | null }) =>
  (a.start ?? '9999').localeCompare(b.start ?? '9999');

/** Étape 1 : l'AMM d'origine ; puis un renouvellement par étape, dans l'ordre des dates. */
export function buildTimeline(preview: DossierImportPreview): {
  steps: TimelineStep[];
  otherDocuments: DossierDocument[];
} {
  const timeline: DossierImportTimelineStep[] = preview.projection?.timeline ?? [];
  const projected = (key: string) => timeline.find((step) => step.key === key);
  const scansOf = (period: string) =>
    preview.documents.filter((doc) => doc.period === period && doc.kind === 'AMM');
  const original = preview.original as Record<string, string | null | undefined>;
  const originProjected = projected('original');
  const origin: TimelineStep = {
    id: 'original',
    kind: 'original',
    title: i18n.t('dossierImports.period.original'),
    number: originProjected?.number || original.original_number || '',
    start: originProjected?.start_date ?? original.original_start_date ?? null,
    end: originProjected?.end_date ?? original.original_end_date ?? null,
    inForce: originProjected?.in_force ?? false,
    isNew: !preview.amm.id,
    inDossier: preview.documents.some((doc) => doc.period === 'original'),
    scans: scansOf('original'),
  };
  const renewals: TimelineStep[] = preview.renewals.map((renewal) => {
    const step = projected(renewal.key);
    return {
      id: renewal.key,
      kind: 'renewal',
      title: renewalTitle(renewal, renewal.key),
      number: step?.number || renewal.number || '',
      start: step?.start_date ?? renewal.start_date ?? renewal.decision_date,
      end: step?.end_date ?? renewal.end_date,
      inForce: step?.in_force ?? false,
      isNew: !renewal.existing_id,
      inDossier: true,
      scans: scansOf(renewal.key),
    };
  });
  // Renouvellements déjà enregistrés dans la fiche mais absents du dossier.
  const recorded: TimelineStep[] = timeline
    .filter((step) => step.key === null)
    .map((step) => ({
      id: `recorded-${step.existing_id ?? step.start_date ?? step.number}`,
      kind: 'renewal',
      title: renewalTitle(step),
      number: step.number,
      start: step.start_date,
      end: step.end_date,
      inForce: step.in_force,
      isNew: false,
      inDossier: false,
      scans: [],
    }));
  const steps = [origin, ...[...renewals, ...recorded].sort(byStart)];
  const shown = new Set(steps.flatMap((step) => step.scans.map((doc) => doc.file_id)));
  const otherDocuments = [...preview.documents]
    .filter((doc) => !shown.has(doc.file_id))
    .sort((a, b) => a.path.localeCompare(b.path));
  return { steps, otherDocuments };
}

export type BatchTone = 'default' | 'success' | 'warning' | 'error' | 'info';

/** Résultat du lot tel que le réglementaire le comprend (historique et en-tête). */
export function batchState(batch: DossierImportBatch): { label: string; tone: BatchTone } {
  switch (batch.status) {
    case 'PENDING':
    case 'RUNNING':
      return { label: i18n.t('dossierImports.state.running'), tone: 'info' };
    case 'FAILED':
      return { label: i18n.t('dossierImports.state.failed'), tone: 'error' };
    case 'APPLIED':
      return { label: i18n.t('dossierImports.state.filed'), tone: 'success' };
    case 'QUESTION':
      return { label: i18n.t('dossierImports.state.question'), tone: 'warning' };
    default:
      return { label: i18n.t('dossierImports.state.toFile'), tone: 'default' };
  }
}

/** L'état en une phrase : « Rangé automatiquement », « Question : c'est quelle AMM ? »… */
export function stateSentence(batch: DossierImportBatch): string {
  switch (batch.status) {
    case 'PENDING':
    case 'RUNNING':
      return i18n.t('dossierImports.sentence.running');
    case 'FAILED':
      return i18n.t('dossierImports.sentence.failed');
    case 'APPLIED':
      return i18n.t(
        batch.auto_applied ? 'dossierImports.sentence.filedAuto' : 'dossierImports.sentence.filed',
      );
    case 'QUESTION':
      return i18n.t('dossierImports.sentence.question');
    default:
      return i18n.t('dossierImports.sentence.ready');
  }
}
