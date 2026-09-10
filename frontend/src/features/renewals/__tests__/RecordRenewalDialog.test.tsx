import { describe, expect, it } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { loginAs, renderApp } from '@/test/utils';
import { db } from '@/mocks/handlers';
import { projectObtainedRenewal } from '@/lib/urgency';

const TODAY = new Date('2026-09-04');

describe('Enregistrement d’un renouvellement obtenu', () => {
  it('projette l’échéance et le statut que le serveur calculera', () => {
    expect(projectObtainedRenewal('2026-08-01', 5, null, TODAY)).toEqual({
      end: '2031-08-01',
      status: 'VALIDE',
    });
    // Une échéance saisie manuellement l'emporte sur la durée de validité du pays.
    expect(projectObtainedRenewal('2026-08-01', 5, '2027-01-31', TODAY).end).toBe('2027-01-31');
    // Une décision ancienne ne ressuscite pas l'AMM.
    expect(projectObtainedRenewal('2019-01-01', 5, null, TODAY).status).toBe('EXPIRE');
    expect(projectObtainedRenewal(null, 5, null, TODAY)).toEqual({ end: null, status: null });
  });

  it('fait repasser une AMM expirée à valide sans rejouer le workflow', async () => {
    const user = userEvent.setup();
    loginAs('u-ceo');
    expect(db.amms.find((a) => a.id === 'amm-8')?.status).toBe('EXPIRE');

    renderApp('/amms/amm-8?tab=renewals');
    expect(await screen.findByText(/Cette AMM est expirée/, {}, { timeout: 5000 })).toBeVisible();
    await user.click(screen.getByTestId('renewal-record'));
    await screen.findByTestId('record-dialog');

    fireEvent.change(screen.getByTestId('record-number'), { target: { value: 'CM-2026-4242' } });
    fireEvent.change(screen.getByTestId('record-start'), { target: { value: '2026-08-01' } });
    const projection = await screen.findByTestId('renewal-projection');
    expect(projection).toHaveTextContent('01/08/2031');
    expect(projection).toHaveTextContent('Valide');

    await user.click(screen.getByTestId('record-submit'));
    await waitFor(() => expect(screen.queryByTestId('record-dialog')).toBeNull());

    const renewal = db.renewals.find((r) => r.amm_id === 'amm-8');
    expect(renewal?.workflow_status).toBe('OBTENU');
    expect(renewal?.number).toBe('CM-2026-4242');
    expect(renewal?.end_date).toBe('2031-08-01');
    const amm = db.amms.find((a) => a.id === 'amm-8');
    expect(amm?.status).toBe('VALIDE');
    expect(amm?.effective_end_date).toBe('2031-08-01');
  });

  it('refuse la saisie sans numéro ni date de début', async () => {
    const user = userEvent.setup();
    loginAs('u-ceo');
    renderApp('/amms/amm-6?tab=renewals');
    await user.click(await screen.findByTestId('renewal-record', {}, { timeout: 5000 }));
    await screen.findByTestId('record-dialog');
    await user.click(screen.getByTestId('record-submit'));
    expect(await screen.findByText(/numéro d’AMM est obligatoire|N° AMM/i)).toBeVisible();
    expect(db.renewals.filter((r) => r.amm_id === 'amm-6')).toHaveLength(0);
  });
});
