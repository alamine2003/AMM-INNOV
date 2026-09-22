import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { loginAs, renderApp } from '@/test/utils';

describe('Fiche AMM — frise et dates de dépôt', () => {
  it('montre l’origine puis le renouvellement obtenu, qui porte le document actuel', async () => {
    loginAs('u-sn');
    renderApp('/amms/amm-1');
    const timeline = await screen.findByTestId('amm-timeline', {}, { timeout: 5000 });
    await within(timeline).findByTestId('timeline-amm-1-ren-1');
    const origin = within(timeline).getByTestId('timeline-origin');
    expect(origin).toHaveTextContent('Origine');
    expect(origin).toHaveTextContent('12/03/2019 → 12/03/2024');
    expect(within(origin).queryByTestId('current-document')).not.toBeInTheDocument();
    const renewal = within(timeline).getByTestId('timeline-amm-1-ren-1');
    expect(renewal).toHaveTextContent('Renouvellement 1');
    expect(within(renewal).getByTestId('current-document')).toHaveTextContent('Document actuel');
    // Dates de dépôt : fin 12/03/2029 − 6 mois et − 3 mois.
    expect(screen.getByTestId('ideal-filing')).toHaveTextContent('12/09/2028');
    expect(screen.getByTestId('agency-deadline')).toHaveTextContent('12/12/2028');
    const header = screen.getAllByTestId('filing-dates')[0];
    expect(header).toHaveTextContent('Dépôt idéal : 12/09/2028');
    expect(header).toHaveTextContent('Limite agence : 12/12/2028');
  });

  it('affiche « À renouveler » et l’état du dossier séparément', async () => {
    loginAs('u-sn');
    renderApp('/amms/amm-2');
    expect(
      (await screen.findAllByTestId('status-chip-A_RENOUVELER', {}, { timeout: 5000 })).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText(/Dossier (complet|incomplet)/).length).toBeGreaterThan(0);
    const timeline = await screen.findByTestId('amm-timeline');
    expect(within(timeline).getByTestId('current-document')).toBeInTheDocument();
  });
});
