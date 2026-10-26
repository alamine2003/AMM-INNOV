import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import '@/lib/i18n';

describe('validation des formulaires', () => {
  it('affiche les messages par défaut en français', () => {
    const result = z.object({ email: z.string().email() }).safeParse({ email: 'pas-un-mail' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].message).toBe('adresse e-mail invalide');
    expect(z.string().min(1).safeParse('').error?.issues[0].message).toBe('Champ obligatoire');
  });
});
