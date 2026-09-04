import { describe, expect, it } from 'vitest';
import { formatDate, formatDateTime, formatRemaining, parseDisplayDate, daysUntil } from '@/lib/dates';

describe('dates', () => {
  it('formate une date ISO en JJ/MM/AAAA', () => {
    expect(formatDate('2026-09-04')).toBe('04/09/2026');
    expect(formatDate('2024-03-12T10:30:00Z')).toBe('12/03/2024');
  });
  it('renvoie le fallback pour une valeur vide ou invalide', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatDate('DATE ILLISIBLE', 'n/a')).toBe('n/a');
  });
  it('formate une date-heure', () => {
    expect(formatDateTime('2026-09-04T08:05:00')).toBe('04/09/2026 08:05');
  });
  it('convertit une saisie JJ/MM/AAAA en ISO', () => {
    expect(parseDisplayDate('12/03/2024')).toBe('2024-03-12');
    expect(parseDisplayDate('31/02/2024')).toBeNull();
    expect(parseDisplayDate('')).toBeNull();
  });
  it('calcule les jours et un libellé de délai restant', () => {
    const today = new Date(2026, 8, 4);
    expect(daysUntil('2026-09-14', today)).toBe(10);
    expect(formatRemaining('2026-09-14', today)).toBe('10 j');
    expect(formatRemaining('2027-01-04', today)).toBe('122 j (4 mois)');
    expect(formatRemaining('2026-08-01', today)).toBe('−34 j (−1 mois)');
  });
});
