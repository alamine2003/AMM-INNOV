import { describe, expect, it } from 'vitest';
import { parseISO } from 'date-fns';
import i18n from '@/lib/i18n';
import {
  AMM_STATUSES,
  filingDates,
  requiredFieldsFor,
  STATUS_COLORS,
  statusFor,
  URGENCIES,
  URGENCY_COLORS,
  WORKFLOW_TRANSITIONS,
} from '@/lib/urgency';

describe('urgence et workflow', () => {
  it('associe les couleurs du PRD aux niveaux d’urgence', () => {
    expect(URGENCY_COLORS.OK).toBe('#2e7d32');
    expect(URGENCY_COLORS.A_PLANIFIER).toBe('#1565c0');
    expect(URGENCY_COLORS.DEPOT_URGENT).toBe('#ef6c00');
    expect(URGENCY_COLORS.CRITIQUE).toBe('#d32f2f');
    expect(URGENCY_COLORS.EXPIRE).toBe('#8e0000');
    expect(URGENCIES).not.toContain('EN_INSTRUCTION');
  });
  it('colore les statuts : vert, orange, rouge, gris', () => {
    expect(AMM_STATUSES).toEqual(['VALIDE', 'A_RENOUVELER', 'EXPIRE', 'INDETERMINE']);
    expect(STATUS_COLORS.VALIDE).toBe('#2e7d32');
    expect(STATUS_COLORS.A_RENOUVELER).toBe('#ef6c00');
    expect(STATUS_COLORS.EXPIRE).toBe('#c62828');
    expect(STATUS_COLORS.INDETERMINE).toBe('#757575');
  });
  it('traduit les libellés d’urgence et de statut en français', () => {
    expect(i18n.t('urgency.DEPOT_URGENT')).toBe('Dépôt urgent');
    expect(i18n.t('urgency.A_PLANIFIER')).toBe('À planifier');
    expect(i18n.t('status.A_RENOUVELER')).toBe('À renouveler');
    expect(i18n.t('status.INDETERMINE')).toBe('Échéance inconnue');
    expect(i18n.t('workflow.EN_INSTRUCTION')).toBe('En instruction');
  });
  it('reflète la machine à états des renouvellements', () => {
    expect(WORKFLOW_TRANSITIONS.EN_PREPARATION).toEqual(['DEPOSE', 'ABANDONNE']);
    expect(WORKFLOW_TRANSITIONS.DEPOSE).toContain('OBTENU');
    expect(WORKFLOW_TRANSITIONS.OBTENU).toEqual([]);
    expect(requiredFieldsFor('DEPOSE')).toEqual(['filing_date']);
    expect(requiredFieldsFor('OBTENU')).toEqual(['number', 'start_date']);
  });
});

describe('statut de validité (miroir du serveur)', () => {
  const end = '2027-07-15';
  it.each([
    ['2027-01-14', 'VALIDE'],
    ['2027-01-15', 'A_RENOUVELER'],
    ['2027-07-15', 'A_RENOUVELER'],
    ['2027-07-16', 'EXPIRE'],
  ])('le %s, une AMM qui finit le 15/07/2027 est %s', (today, expected) => {
    expect(statusFor(end, parseISO(today))).toBe(expected);
  });
  it('sans date de fin : échéance inconnue', () => {
    expect(statusFor(null)).toBe('INDETERMINE');
  });
  it('dépôt idéal = fin − 6 mois, limite agence = fin − 3 mois', () => {
    expect(filingDates('2027-08-31')).toEqual({ ideal: '2027-02-28', agency: '2027-05-31' });
  });
});
