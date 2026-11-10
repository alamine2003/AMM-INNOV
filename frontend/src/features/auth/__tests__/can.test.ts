import { describe, expect, it } from 'vitest';
import type { User } from '@/api/types';
import { can } from '../authStore';

const base: User = {
  id: 'u',
  email: 'u@test',
  first_name: 'U',
  last_name: 'T',
  role: 'HQ_REGULATORY',
  countries: [],
};

describe('can (droits donnés par le backend)', () => {
  it('suit la liste `actions` renvoyée par /me, pas le rôle', () => {
    expect(can({ ...base, actions: ['binder.download'] }, 'binder.download')).toBe(true);
    expect(can({ ...base, actions: ['binder.download'] }, 'binder.delete_page')).toBe(false);
  });

  it('refuse sans utilisateur ou sans liste', () => {
    expect(can(null, 'binder.download')).toBe(false);
    expect(can(base, 'binder.download')).toBe(false);
  });
});
