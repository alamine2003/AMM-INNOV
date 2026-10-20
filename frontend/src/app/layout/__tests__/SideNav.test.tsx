import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { loginAs, renderApp } from '@/test/utils';
import { useSidebarStore } from '../sidebarStore';

describe('Menu latéral', () => {
  it('se réduit aux icônes, garde les libellés en info-bulle et retient le choix', async () => {
    localStorage.removeItem('amm-gh.sidebar');
    useSidebarStore.setState({ collapsed: false });
    loginAs('u-sn');
    renderApp('/');
    const sidebar = await screen.findByTestId('sidebar');
    expect(sidebar).toHaveAttribute('data-collapsed', 'false');
    await userEvent.click(screen.getByRole('button', { name: 'Réduire le menu' }));
    expect(sidebar).toHaveAttribute('data-collapsed', 'true');
    expect(localStorage.getItem('amm-gh.sidebar')).toBe('collapsed');
    // Les entrées restent accessibles par leur nom (info-bulle et aria-label).
    expect(screen.getAllByRole('link', { name: 'Classeurs' }).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole('button', { name: 'Agrandir le menu' }));
    expect(sidebar).toHaveAttribute('data-collapsed', 'false');
    expect(localStorage.getItem('amm-gh.sidebar')).toBe('open');
  });
});
