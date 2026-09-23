import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { db } from '@/mocks/handlers';
import { loginAs, renderApp } from '@/test/utils';

describe('Grille AMM', () => {
  it('filtre les AMM par statut via l’URL', async () => {
    loginAs('u-hq');
    renderApp('/amms?status=EXPIRE');
    await waitFor(() => expect(screen.getAllByTestId('status-chip-EXPIRE').length).toBeGreaterThan(0), {
      timeout: 5000,
    });
    expect(screen.queryByTestId('status-chip-VALIDE')).not.toBeInTheDocument();
    expect(screen.getByText(/2 AMM/)).toBeInTheDocument();
  });

  it('affiche toutes les AMM du périmètre sans filtre', async () => {
    loginAs('u-hq');
    renderApp('/amms');
    expect(await screen.findByText(/10 AMM/, {}, { timeout: 5000 })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByTestId(/scan-(present|missing)/).length).toBeGreaterThan(0));
  });

  it('signale par un badge les points à vérifier laissés par l’import de dossiers', async () => {
    db.amms[0].open_review_points = 2;
    loginAs('u-hq');
    renderApp('/amms');
    expect(await screen.findByLabelText('2 point(s) à vérifier', {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getAllByTestId('review-points-badge')).toHaveLength(1);
  });
});
