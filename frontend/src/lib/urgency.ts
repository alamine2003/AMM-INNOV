import { addYears, parseISO } from 'date-fns';
import type { AlertStatus, AmmStatus, DossierState, Severity, Urgency, WorkflowStatus } from '@/api/types';
import { toApiDate } from '@/lib/dates';

export const URGENCY_COLORS: Record<Urgency, string> = {
  OK: '#2e7d32',
  A_PLANIFIER: '#1565c0',
  DEPOT_URGENT: '#ef6c00',
  CRITIQUE: '#d32f2f',
  EXPIRE: '#8e0000',
  EN_INSTRUCTION: '#6a1b9a',
};

export const STATUS_COLORS: Record<AmmStatus, string> = {
  VALIDE: '#2e7d32',
  EXPIRE: '#c62828',
  IN_PROCESS: '#6a1b9a',
  INDETERMINE: '#757575',
};

export const WORKFLOW_COLORS: Record<WorkflowStatus, string> = {
  PLANIFIE: '#546e7a',
  EN_PREPARATION: '#1565c0',
  DEPOSE: '#ef6c00',
  EN_INSTRUCTION: '#6a1b9a',
  OBTENU: '#2e7d32',
  REJETE: '#c62828',
  ABANDONNE: '#616161',
};

export const SEVERITY_COLORS: Record<Severity, string> = {
  INFO: '#1565c0',
  WARNING: '#ef6c00',
  CRITICAL: '#c62828',
};

export const ALERT_STATUS_COLORS: Record<AlertStatus, string> = {
  OPEN: '#c62828',
  ACKNOWLEDGED: '#ef6c00',
  RESOLVED: '#2e7d32',
};

export const DOSSIER_COLORS: Record<DossierState, string> = {
  COMPLET: '#2e7d32',
  INCOMPLET: '#ef6c00',
};

export const URGENCY_ORDER: Urgency[] = [
  'EXPIRE',
  'CRITIQUE',
  'DEPOT_URGENT',
  'EN_INSTRUCTION',
  'A_PLANIFIER',
  'OK',
];
/** Urgences encore actionnables, dans l'ordre de traitement (listes de priorités). */
export const PRIORITY_URGENCIES: Urgency[] = ['CRITIQUE', 'DEPOT_URGENT', 'A_PLANIFIER'];
export const AMM_STATUSES: AmmStatus[] = ['VALIDE', 'EXPIRE', 'IN_PROCESS', 'INDETERMINE'];
export const URGENCIES: Urgency[] = [
  'OK',
  'A_PLANIFIER',
  'DEPOT_URGENT',
  'CRITIQUE',
  'EXPIRE',
  'EN_INSTRUCTION',
];
export const DOSSIER_STATES: DossierState[] = ['COMPLET', 'INCOMPLET'];
export const WORKFLOW_STATUSES: WorkflowStatus[] = [
  'PLANIFIE',
  'EN_PREPARATION',
  'DEPOSE',
  'EN_INSTRUCTION',
  'OBTENU',
  'REJETE',
  'ABANDONNE',
];

/** Machine à états (miroir de la règle backend) : état → transitions autorisées. */
export const WORKFLOW_TRANSITIONS: Record<WorkflowStatus, WorkflowStatus[]> = {
  PLANIFIE: ['EN_PREPARATION', 'ABANDONNE'],
  EN_PREPARATION: ['DEPOSE', 'ABANDONNE'],
  DEPOSE: ['EN_INSTRUCTION', 'OBTENU', 'ABANDONNE'],
  EN_INSTRUCTION: ['OBTENU', 'REJETE', 'ABANDONNE'],
  OBTENU: [],
  REJETE: [],
  ABANDONNE: [],
};

export const TERMINAL_STATES: WorkflowStatus[] = ['OBTENU', 'REJETE', 'ABANDONNE'];

/**
 * Prévisualisation de ce que le serveur calculera en enregistrant un renouvellement obtenu :
 * échéance = début + durée de validité du pays (sauf saisie manuelle), puis statut de l'AMM.
 * Le serveur reste la source de vérité ; cette projection ne sert qu'à l'affichage.
 */
export function projectObtainedRenewal(
  startDate: string | null | undefined,
  validityYears: number,
  manualEnd?: string | null,
  today = new Date(),
): { end: string | null; status: AmmStatus | null } {
  const end = manualEnd || (startDate ? toApiDate(addYears(parseISO(startDate), validityYears)) : null);
  if (!end) return { end: null, status: null };
  return { end, status: parseISO(end) >= parseISO(toApiDate(today)) ? 'VALIDE' : 'EXPIRE' };
}

/** Champs obligatoires pour une transition donnée. */
export function requiredFieldsFor(to: WorkflowStatus): ('filing_date' | 'number' | 'start_date')[] {
  if (to === 'DEPOSE') return ['filing_date'];
  if (to === 'OBTENU') return ['number', 'start_date'];
  return [];
}
