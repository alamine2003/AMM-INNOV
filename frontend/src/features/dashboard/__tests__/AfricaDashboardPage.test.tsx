import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { loginAs, renderApp } from '@/test/utils';

describe('Dashboard Afrique', () => {
  it('affiche une ligne par pays et la ligne TOTAL calculées depuis MSW', async () => {
    loginAs('u-hq');
    renderApp('/');
    const table = await screen.findByTestId('africa-table', {}, { timeout: 5000 });
    expect(within(table).getByTestId('africa-row-SN')).toHaveTextContent('Sénégal');
    expect(within(table).getByTestId('africa-row-CI')).toHaveTextContent("Côte d'Ivoire");
    expect(within(table).getByTestId('africa-row-CM')).toHaveTextContent('Cameroun');
    const total = within(table).getByTestId('africa-total-row');
    expect(total).toHaveTextContent('TOTAL');
    const cells = within(total).getAllByRole('cell');
    expect(cells[1]).toHaveTextContent('10');
  });

  it('restreint un réglementaire pays à son périmètre', async () => {
    loginAs('u-sn');
    renderApp('/');
    const table = await screen.findByTestId('africa-table', {}, { timeout: 5000 });
    expect(within(table).getByTestId('africa-row-SN')).toBeInTheDocument();
    expect(within(table).queryByTestId('africa-row-CI')).not.toBeInTheDocument();
    const cells = within(within(table).getByTestId('africa-total-row')).getAllByRole('cell');
    expect(cells[1]).toHaveTextContent('4');
  });
});
