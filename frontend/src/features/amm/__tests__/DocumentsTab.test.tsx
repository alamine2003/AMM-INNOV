import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { loginAs, renderApp } from '@/test/utils';

describe('Fiche AMM — onglet Documents', () => {
  it('affiche les périodes et documents du plus récent au plus ancien avec le badge En vigueur', async () => {
    loginAs('u-sn');
    renderApp('/amms/amm-1?tab=documents');
    const timeline = await screen.findByTestId('document-timeline', {}, { timeout: 5000 });
    const periods = within(timeline).getAllByTestId(/^period-/);
    expect(periods[0]).toHaveAttribute('data-testid', 'period-RENEWAL-1');
    expect(periods[periods.length - 1]).toHaveAttribute('data-testid', 'period-ORIGINAL-0');
    const docs = within(timeline).getAllByTestId(/^document-doc-/);
    expect(docs.map((d) => d.getAttribute('data-testid'))).toEqual([
      'document-doc-1',
      'document-doc-2',
      'document-doc-3',
    ]);
    const badge = within(timeline).getByTestId('badge-current');
    expect(within(docs[0]).getByTestId('badge-current')).toBe(badge);
    expect(badge).toHaveTextContent('En vigueur');
  });
});
