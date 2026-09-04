import { describe, expect, it } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { loginAs, renderApp } from '@/test/utils';
import { db } from '@/mocks/handlers';
import { buildTransitionSchema } from '@/features/renewals/TransitionDialog';

describe('Transition de renouvellement', () => {
  it('le schéma refuse DEPOSE sans date de dépôt et OBTENU sans numéro/date', () => {
    const t = (k: string) => k;
    expect(buildTransitionSchema('DEPOSE', t).safeParse({ filing_date: null }).success).toBe(false);
    expect(buildTransitionSchema('DEPOSE', t).safeParse({ filing_date: '2026-09-04' }).success).toBe(true);
    expect(buildTransitionSchema('OBTENU', t).safeParse({ number: '', start_date: null }).success).toBe(
      false,
    );
    expect(
      buildTransitionSchema('OBTENU', t).safeParse({ number: 'SN-1', start_date: '2026-09-04' }).success,
    ).toBe(true);
    expect(buildTransitionSchema('ABANDONNE', t).safeParse({}).success).toBe(true);
  });

  it('le dialogue refuse DEPOSE sans filing_date puis accepte avec la date', async () => {
    const user = userEvent.setup();
    loginAs('u-ci');
    renderApp('/amms/amm-10?tab=renewals');
    await user.click(await screen.findByTestId('transition-DEPOSE', {}, { timeout: 5000 }));
    const dialog = await screen.findByTestId('transition-dialog');
    expect(dialog).toBeInTheDocument();
    await user.click(screen.getByTestId('transition-submit'));
    expect(
      await screen.findByText('La date de dépôt est obligatoire pour passer à « Déposé »'),
    ).toBeInTheDocument();
    expect(db.renewals.find((r) => r.id === 'amm-10-ren-1')?.workflow_status).toBe('EN_PREPARATION');

    fireEvent.change(screen.getByTestId('filing_date'), { target: { value: '2026-09-04' } });
    await user.click(screen.getByTestId('transition-submit'));
    await waitFor(() =>
      expect(db.renewals.find((r) => r.id === 'amm-10-ren-1')?.workflow_status).toBe('DEPOSE'),
    );
    expect(db.renewals.find((r) => r.id === 'amm-10-ren-1')?.filing_date).toBe('2026-09-04');
  });
});
