import type { DepositDetail, DepositStage, DepositSummary } from '@/api/types';

/** Couleur de chaque étape : du bleu du siège au vert de la décision obtenue. */
export const STAGE_COLORS: Record<DepositStage, string> = {
  MONTAGE: '#5c6bc0',
  ENVOYE: '#0288d1',
  DEPOSE: '#00897b',
  COMMISSION: '#f57c00',
  OBTENU: '#2e7d32',
  REJETE: '#c62828',
  ABANDONNE: '#757575',
};

export const CLOSED_STAGES: DepositStage[] = ['OBTENU', 'REJETE', 'ABANDONNE'];

/** La procédure du siège, telle qu'elle est suivie dans l'application. */
export const PROCEDURE = [
  {
    title: 'Montage du dossier',
    who: 'Siège',
    text: 'Lettre de demande de renouvellement, certificat de PGHT (prix grossiste hors taxe), formulaires, RCP, certificats d’analyse, pièces réglementaires du pays.',
  },
  {
    title: 'Échantillons',
    who: 'Siège',
    text: 'Récupérer les échantillons sur place et noter n° de lot, date de fabrication et date de péremption.',
  },
  {
    title: 'Envoi au pays',
    who: 'Siège',
    text: 'Le dossier part au pays : il est prévenu et télécharge le dossier complet depuis l’application.',
  },
  {
    title: 'Dépôt à l’agence',
    who: 'Pays',
    text: 'Le pays dépose le dossier à l’agence de régulation et envoie l’attestation de dépôt au siège.',
  },
  {
    title: 'Commission',
    who: 'Pays',
    text: 'Le dépôt passe en commission ; chaque commission et chaque notification de l’agence est notée.',
  },
  {
    title: 'Décision',
    who: 'Pays ou siège',
    text: 'Renouvellement obtenu (n° et date de début) ou rejeté : le dossier est clos et l’AMM recalculée.',
  },
] as const;

export const STAGE_STEP: Record<DepositStage, number> = {
  MONTAGE: 0,
  ENVOYE: 3,
  DEPOSE: 4,
  COMMISSION: 4,
  OBTENU: 6,
  REJETE: 6,
  ABANDONNE: 6,
};

/** Étapes terminées, dans l'ordre de la procédure (6 étapes). */
export function stepsDone(dossier: DepositDetail): boolean[] {
  const piecesOk = dossier.pieces_done >= dossier.pieces_required;
  const samplesOk = !dossier.samples_required || dossier.samples_count > 0;
  const sent = !!dossier.sent_at;
  const deposited = ['DEPOSE', 'COMMISSION', 'OBTENU', 'REJETE'].includes(dossier.stage);
  const decided = dossier.stage === 'OBTENU' || dossier.stage === 'REJETE';
  const commission = decided || dossier.stage === 'COMMISSION';
  return [piecesOk || sent, samplesOk || sent, sent, deposited, commission, decided];
}

/** Étape en cours : la première qui n'est pas faite. */
export function activeStep(dossier: DepositDetail): number {
  const done = stepsDone(dossier);
  const first = done.findIndex((value) => !value);
  return first === -1 ? done.length : first;
}

export function isClosed(dossier: Pick<DepositSummary, 'stage'>): boolean {
  return CLOSED_STAGES.includes(dossier.stage);
}
