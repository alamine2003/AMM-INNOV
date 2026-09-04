import { describe, expect, it } from 'vitest';
import i18n from '@/lib/i18n';
import { requiredFieldsFor, URGENCY_COLORS, WORKFLOW_TRANSITIONS } from '@/lib/urgency';

describe('urgence et workflow', () => {
  it('associe les couleurs du PRD aux niveaux d’urgence', () => {
    expect(URGENCY_COLORS.OK).toBe('#2e7d32');
    expect(URGENCY_COLORS.A_PLANIFIER).toBe('#1565c0');
    expect(URGENCY_COLORS.DEPOT_URGENT).toBe('#ef6c00');
    expect(URGENCY_COLORS.CRITIQUE).toBe('#d32f2f');
    expect(URGENCY_COLORS.EXPIRE).toBe('#8e0000');
    expect(URGENCY_COLORS.EN_INSTRUCTION).toBe('#6a1b9a');
  });
  it('traduit les libellés d’urgence et de statut en français', () => {
    expect(i18n.t('urgency.DEPOT_URGENT')).toBe('Dépôt urgent');
    expect(i18n.t('urgency.A_PLANIFIER')).toBe('À planifier');
    expect(i18n.t('status.IN_PROCESS')).toBe('En cours');
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
