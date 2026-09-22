/**
 * Lecture « métier » d'un aperçu d'import de dossier : étapes de la chronologie d'une AMM
 * (origine puis renouvellements), état du lot en français simple, messages sans clé technique.
 */
import type {
  DossierImportBatch,
  DossierImportChange,
  DossierImportPreview,
  DossierImportTimelineStep,
} from '@/api/types';
import { formatDate } from '@/lib/dates';

export const fieldLabels: Record<string, string> = {
  original_number: 'N° d’AMM',
  original_start_date: 'Date de délivrance',
  original_end_date: 'Date d’échéance',
  holder: 'Titulaire',
  number: 'N° de renouvellement',
  start_date: 'Date de début',
  end_date: 'Date de fin',
  decision_date: 'Date de décision',
  workflow_status: 'État du renouvellement',
};

const workflowLabels: Record<string, string> = {
  PLANIFIE: 'Planifié',
  EN_PREPARATION: 'En préparation',
  DEPOSE: 'Déposé',
  EN_INSTRUCTION: 'En instruction',
  OBTENU: 'Obtenu',
  REJETE: 'Rejeté',
  ABANDONNE: 'Abandonné',
};

export const documentKindLabels: Record<string, string> = {
  AMM: 'Décision',
  RECEPISSE: 'Récépissé de dépôt',
  COURRIER: 'Courrier de l’autorité',
  AUTRE: 'Autre document',
};

/** Valeur lisible d'un champ (dates au format français, états traduits). */
export function showValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return 'vide';
  if (field.endsWith('date')) return formatDate(String(value));
  if (field === 'workflow_status') return workflowLabels[String(value)] ?? String(value);
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
  if (date) return `Renouvellement du ${formatDate(date)}`;
  const year = /(?:^|\D)((?:19|20)\d{2})(?:\D|$)/.exec(key)?.[1];
  return year ? `Renouvellement de ${year}` : 'Renouvellement (date non lue)';
}

export function periodTitle(period: string, preview: DossierImportPreview): string {
  if (period === 'original') return 'AMM d’origine';
  return renewalTitle(preview.renewals.find((renewal) => renewal.key === period) ?? null, period);
}

/** Traduit un blocage ou un avertissement du serveur : périodes et champs nommés en clair. */
export function humanize(message: string, preview: DossierImportPreview): string {
  return message
    .replace(/renewal-[\w-]*\w/g, (key) => periodTitle(key, preview))
    .replace(
      /(contradictoires pour .+?) : (\w+)\./,
      (_, head: string, field: string) => `${head} : ${(fieldLabels[field] ?? field).toLowerCase()}.`,
    )
    .replace('Preuves officielles contradictoires pour', 'Les décisions se contredisent pour');
}

export type StepAction = 'recorded' | 'added' | 'completed' | 'review';

export const actionLabels: Record<StepAction, string> = {
  recorded: 'Déjà enregistré',
  added: 'Sera ajouté',
  completed: 'Sera complété',
  review: 'À vérifier',
};

export interface TimelineStep {
  id: string;
  kind: 'original' | 'renewal';
  title: string;
  number: string;
  start: string | null;
  end: string | null;
  inForce: boolean;
  inDossier: boolean;
  action: StepAction;
  confidence: number | null;
  /** Écarts avec la base : le réglementaire choisit de garder ou de remplacer. */
  choices: DossierImportChange[];
  /** Champs vides complétés d'office. */
  completions: DossierImportChange[];
  scans: DossierDocument[];
}

const byStart = (a: { start: string | null }, b: { start: string | null }) =>
  (a.start ?? '9999').localeCompare(b.start ?? '9999');

function actionFor(isNew: boolean, choices: unknown[], completions: unknown[], confidence: number | null) {
  if (choices.length || (confidence !== null && confidence < 90)) return 'review';
  if (isNew) return 'added';
  return completions.length ? 'completed' : 'recorded';
}

/** Étape 1 : l'AMM d'origine ; puis un renouvellement par étape, dans l'ordre des dates. */
export function buildTimeline(preview: DossierImportPreview): {
  steps: TimelineStep[];
  otherDocuments: DossierDocument[];
} {
  const timeline: DossierImportTimelineStep[] = preview.projection?.timeline ?? [];
  const projected = (key: string) => timeline.find((step) => step.key === key);
  const changesOf = (target: string) => preview.changes.filter((change) => change.target === target);
  const scansOf = (period: string) =>
    preview.documents.filter((doc) => doc.period === period && doc.kind === 'AMM');
  const original = preview.original as Record<string, string | null | undefined>;
  const originChanges = changesOf('amm');
  const originChoices = originChanges.filter((change) => change.requires_confirmation);
  const originCompletions = originChanges.filter((change) => !change.requires_confirmation);
  const originProjected = projected('original');
  const origin: TimelineStep = {
    id: 'original',
    kind: 'original',
    title: 'AMM d’origine',
    number: originProjected?.number || original.original_number || '',
    start: originProjected?.start_date ?? original.original_start_date ?? null,
    end: originProjected?.end_date ?? original.original_end_date ?? null,
    inForce: originProjected?.in_force ?? false,
    inDossier: preview.documents.some((doc) => doc.period === 'original'),
    action: actionFor(!preview.amm.id, originChoices, originCompletions, null),
    confidence: null,
    choices: originChoices,
    completions: originCompletions,
    scans: scansOf('original'),
  };
  const renewals: TimelineStep[] = preview.renewals.map((renewal) => {
    const changes = changesOf(renewal.key);
    const choices = changes.filter((change) => change.requires_confirmation);
    const completions = changes.filter((change) => !change.requires_confirmation);
    const step = projected(renewal.key);
    return {
      id: renewal.key,
      kind: 'renewal',
      title: renewalTitle(renewal, renewal.key),
      number: step?.number || renewal.number || '',
      start: step?.start_date ?? renewal.start_date ?? renewal.decision_date,
      end: step?.end_date ?? renewal.end_date,
      inForce: step?.in_force ?? false,
      inDossier: true,
      action: actionFor(!renewal.existing_id, choices, completions, renewal.confidence),
      confidence: renewal.confidence,
      choices,
      completions,
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
      inDossier: false,
      action: 'recorded',
      confidence: null,
      choices: [],
      completions: [],
      scans: [],
    }));
  const steps = [origin, ...[...renewals, ...recorded].sort(byStart)];
  const shown = new Set(steps.flatMap((step) => step.scans.map((doc) => doc.file_id)));
  const otherDocuments = [...preview.documents]
    .filter((doc) => !shown.has(doc.file_id))
    .sort((a, b) => a.path.localeCompare(b.path));
  return { steps, otherDocuments };
}

export function isBlocked(preview: DossierImportPreview | null): boolean {
  return !preview || !preview.can_apply || preview.level === 'LOW' || preview.blockers.length > 0;
}

/** Phrases des blocages, sans clé technique. */
export function blockingReasons(preview: DossierImportPreview | null): string[] {
  if (!preview) return ['L’analyse n’a produit aucun aperçu : relancez-la.'];
  const reasons = preview.blockers.map((message) => humanize(message, preview));
  if (preview.level === 'LOW')
    reasons.push(
      `Lecture trop incertaine (${preview.confidence} %) : aucune donnée ne peut être modifiée. Vérifiez les documents puis relancez l’analyse.`,
    );
  if (!reasons.length && !preview.can_apply) reasons.push('Validation impossible : relancez l’analyse.');
  return reasons;
}

/** Ce que le réglementaire doit regarder avant de valider. */
export function reviewPoints(preview: DossierImportPreview): string[] {
  const points = preview.changes
    .filter((change) => change.requires_confirmation)
    .map(
      (change) =>
        `${fieldLabels[change.field] ?? change.field} (${
          change.target === 'amm' ? 'AMM d’origine' : periodTitle(change.target, preview)
        }) : le scan ne dit pas la même chose que la fiche, choisissez la valeur à garder.`,
    );
  points.push(...preview.warnings.map((message) => humanize(message, preview)));
  if (preview.level === 'MEDIUM')
    points.push(
      `Lecture moyennement sûre (${preview.confidence} %) : vérifiez les dates et le numéro sur les scans.`,
    );
  return points;
}

const plural = (count: number) => `${count} point${count > 1 ? 's' : ''}`;

export type BatchTone = 'default' | 'success' | 'warning' | 'error' | 'info';

/** État du lot tel que le réglementaire le comprend (historique et en-tête). */
export function batchState(batch: DossierImportBatch): { label: string; tone: BatchTone } {
  switch (batch.status) {
    case 'PENDING':
    case 'RUNNING':
      return { label: 'Analyse en cours', tone: 'info' };
    case 'FAILED':
      return { label: 'Échec de l’analyse', tone: 'error' };
    case 'APPLIED':
      return batch.auto_applied
        ? { label: 'Validé automatiquement', tone: 'success' }
        : { label: 'Validé', tone: 'success' };
    default: {
      if (isBlocked(batch.preview)) return { label: 'Bloqué', tone: 'error' };
      const count = reviewPoints(batch.preview!).length;
      return count
        ? { label: `À vérifier (${plural(count)})`, tone: 'warning' }
        : { label: 'Prêt à valider', tone: 'default' };
    }
  }
}

/** Phrase d'état de l'en-tête : « Prêt à valider », « À vérifier : 2 points », « Bloqué : … ». */
export function stateSentence(preview: DossierImportPreview | null): string {
  if (isBlocked(preview)) return `Bloqué : ${blockingReasons(preview)[0]}`;
  const count = reviewPoints(preview!).length;
  return count ? `À vérifier : ${plural(count)}` : 'Prêt à valider';
}

export const ammStatusLabels: Record<string, string> = {
  VALIDE: 'Valide',
  A_RENOUVELER: 'À renouveler',
  EXPIRE: 'Expirée',
  INDETERMINE: 'Échéance inconnue',
};
