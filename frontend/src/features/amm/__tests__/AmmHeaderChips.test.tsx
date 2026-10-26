import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { loginAs, renderApp } from '@/test/utils';
import { db } from '@/mocks/handlers';

describe('Fiche AMM — en-tête', () => {
  it("n'affiche pas deux fois « Expirée » pour une AMM expirée", async () => {
    loginAs('u-ceo');
    const expired = db.amms.find((a) => a.status === 'EXPIRE');
    expect(expired).toBeDefined();
    renderApp(`/amms/${expired!.id}`);
    expect((await screen.findAllByTestId('status-chip-EXPIRE')).length).toBeGreaterThan(0);
    expect(screen.queryByTestId('urgency-chip-EXPIRE')).not.toBeInTheDocument();
  });
});
