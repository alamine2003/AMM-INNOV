import { describe, expect, it } from 'vitest';
import { navItemsForRole } from '@/app/layout/navigation';

describe('menu par rôle', () => {
  it('masque l’administration au réglementaire pays', () => {
    const keys = navItemsForRole('COUNTRY_REGULATORY').map((i) => i.key);
    expect(keys).toEqual(['dashboard', 'amms', 'alerts', 'documents', 'products']);
  });
  it('expose l’administration au siège et au CEO', () => {
    expect(navItemsForRole('HQ_REGULATORY').map((i) => i.key)).toContain('users');
    expect(navItemsForRole('CEO_ADMIN').map((i) => i.key)).toContain('imports');
  });
});
