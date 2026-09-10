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

  it('conclut le renouvellement en cours au lieu d’en créer un second', async () => {
    const user = userEvent.setup();
    loginAs('u-ceo');
    const pending = db.renewals.filter((r) => r.amm_id === 'amm-5');
    expect(pending).toHaveLength(1);
    expect(pending[0].workflow_status).toBe('DEPOSE');
    const filedOn = pending[0].filing_date; // relevé avant : le mock mute l'objet en place

    renderApp('/amms/amm-5?tab=renewals');
    expect(
      await screen.findByText(/Un renouvellement est déjà en cours/, {}, { timeout: 5000 }),
    ).toBeVisible();
    await user.click(screen.getByTestId('renewal-record'));
    await screen.findByTestId('record-dialog');
    fireEvent.change(screen.getByTestId('record-number'), { target: { value: 'CI-2026-0808' } });
    fireEvent.change(screen.getByTestId('record-start'), { target: { value: '2026-08-01' } });
    await user.click(screen.getByTestId('record-submit'));
    await waitFor(() => expect(screen.queryByTestId('record-dialog')).toBeNull());

    const renewals = db.renewals.filter((r) => r.amm_id === 'amm-5');
    expect(renewals).toHaveLength(1);
    expect(renewals[0].workflow_status).toBe('OBTENU');
    expect(renewals[0].number).toBe('CI-2026-0808');
    // La date de dépôt du renouvellement en cours est conservée : c'est le même dossier.
    expect(renewals[0].filing_date).toBe(filedOn);
    expect(db.amms.find((a) => a.id === 'amm-5')?.status).toBe('VALIDE');
  });

  it('annule un renouvellement ajouté par erreur et rend l’AMM à son état précédent', async () => {
    const user = userEvent.setup();
    loginAs('u-ceo');
    // amm-8 porte le scan de son AMM d'origine : son dossier est complet avant l'ajout.
    expect(db.amms.find((a) => a.id === 'amm-8')?.dossier_state).toBe('COMPLET');
    renderApp('/amms/amm-8?tab=renewals');

    // On ajoute, puis on revient en arrière.
    await user.click(await screen.findByTestId('renewal-record', {}, { timeout: 5000 }));
    await screen.findByTestId('record-dialog');
    fireEvent.change(screen.getByTestId('record-number'), { target: { value: 'CM-2026-9999' } });
    fireEvent.change(screen.getByTestId('record-start'), { target: { value: '2026-08-01' } });
    await user.click(screen.getByTestId('record-submit'));
    await waitFor(() => expect(db.amms.find((a) => a.id === 'amm-8')?.status).toBe('VALIDE'));
    // La décision qui fait foi est désormais le renouvellement, et lui n'a pas de scan.
    expect(db.amms.find((a) => a.id === 'amm-8')?.dossier_state).toBe('INCOMPLET');

    await user.click(await screen.findByTestId('renewal-cancel-1'));
    await screen.findByTestId('cancel-dialog');
    await user.click(screen.getByTestId('cancel-submit'));
    await waitFor(() => expect(screen.queryByTestId('cancel-dialog')).toBeNull());

    expect(db.renewals.filter((r) => r.amm_id === 'amm-8')).toHaveLength(0);
    const amm = db.amms.find((a) => a.id === 'amm-8');
    expect(amm?.status).toBe('EXPIRE');
    // L'AMM d'origine redevient la décision en vigueur : son scan la prouve de nouveau.
    expect(amm?.dossier_state).toBe('COMPLET');
  });

  it('refuse la saisie sans numéro ni date de début', async () => {
    const user = userEvent.setup();
    loginAs('u-ceo');
    renderApp('/amms/amm-6?tab=renewals');
    await user.click(await screen.findByTestId('renewal-record', {}, { timeout: 5000 }));
    await screen.findByTestId('record-dialog');
    await user.click(screen.getByTestId('record-submit'));
    expect(await screen.findByText("Le numéro d'AMM est obligatoire pour passer à « Obtenu »")).toBeVisible();
    expect(screen.getByText('La date de début est obligatoire pour passer à « Obtenu »')).toBeVisible();
    expect(db.renewals.filter((r) => r.amm_id === 'amm-6')).toHaveLength(0);
  });
});
