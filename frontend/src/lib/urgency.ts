import { addYears, parseISO, subMonths } from 'date-fns';
import type { AlertStatus, AmmStatus, DossierState, Severity, Urgency, WorkflowStatus } from '@/api/types';
import { toApiDate } from '@/lib/dates';

export const URGENCY_COLORS: Record<Urgency, string> = {
  OK: '#2e7d32',
  A_PLANIFIER: '#1565c0',
  DEPOT_URGENT: '#ef6c00',
  CRITIQUE: '#d32f2f',
  EXPIRE: '#8e0000',
};

/** Valide (vert), À renouveler (orange), Expirée (rouge), Échéance inconnue (gris). */
export const STATUS_COLORS: Record<AmmStatus, string> = {
  VALIDE: '#2e7d32',
  A_RENOUVELER: '#ef6c00',
  EXPIRE: '#c62828',
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

export const URGENCY_ORDER: Urgency[] = ['EXPIRE', 'CRITIQUE', 'DEPOT_URGENT', 'A_PLANIFIER', 'OK'];
/** Urgences encore actionnables, dans l'ordre de traitement (listes de priorités). */
export const PRIORITY_URGENCIES: Urgency[] = ['CRITIQUE', 'DEPOT_URGENT', 'A_PLANIFIER'];
export const AMM_STATUSES: AmmStatus[] = ['VALIDE', 'A_RENOUVELER', 'EXPIRE', 'INDETERMINE'];
export const URGENCIES: Urgency[] = ['OK', 'A_PLANIFIER', 'DEPOT_URGENT', 'CRITIQUE', 'EXPIRE'];
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
  return { end, status: statusFor(end, today) };
}

/**
 * Miroir de `derive_status` (backend) pour l'affichage : expirée quand aujourd'hui > fin,
 * « À renouveler » dès fin − 6 mois (jour J compris), sinon valide.
 */
export function statusFor(end: string | null | undefined, today = new Date()): AmmStatus {
  if (!end) return 'INDETERMINE';
  const day = toApiDate(today);
  if (day > end) return 'EXPIRE';
  return day >= filingDates(end).ideal ? 'A_RENOUVELER' : 'VALIDE';
}

/** Dépôt idéal = fin − 6 mois ; limite agence = fin − 3 mois (mêmes règles que le serveur). */
export function filingDates(end: string): { ideal: string; agency: string } {
  const date = parseISO(end);
  return { ideal: toApiDate(subMonths(date, 6)), agency: toApiDate(subMonths(date, 3)) };
}

/** Champs obligatoires pour une transition donnée. */
export function requiredFieldsFor(to: WorkflowStatus): ('filing_date' | 'number' | 'start_date')[] {
  if (to === 'DEPOSE') return ['filing_date'];
  if (to === 'OBTENU') return ['number', 'start_date'];
  return [];
}
