import { describe, expect, it } from 'vitest';
import en from '@/locales/en.json';
import fr from '@/locales/fr.json';

type Tree = { [key: string]: string | Tree };

/** « amm.filters.country » → texte, pour toutes les feuilles du fichier de langue. */
function flatten(tree: Tree, prefix = ''): Record<string, string> {
  return Object.entries(tree).reduce<Record<string, string>>((all, [key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === 'string' ? { ...all, [path]: value } : { ...all, ...flatten(value, path) };
  }, {});
}

const variables = (text: string) => [...text.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]).sort();

describe('fichiers de langue', () => {
  const french = flatten(fr as Tree);
  const english = flatten(en as Tree);

  it('ont exactement les mêmes clés : aucun texte ne manque dans une langue', () => {
    expect(Object.keys(english).sort()).toEqual(Object.keys(french).sort());
  });

  it("n'ont aucun texte vide", () => {
    for (const [key, text] of [...Object.entries(french), ...Object.entries(english)]) {
      expect(text.trim(), key).not.toBe('');
    }
  });

  it('gardent les mêmes variables ({{count}}, {{date}}…) dans les deux langues', () => {
    for (const key of Object.keys(french)) {
      expect(variables(english[key] ?? ''), key).toEqual(variables(french[key]));
    }
  });

  it('traduisent vraiment : peu de textes sont identiques dans les deux langues', () => {
    // Noms propres, sigles et mots communs (« Documents », « Date », « Code ») : une petite part.
    const same = Object.keys(french).filter((key) => french[key] === english[key]);
    expect(same.length / Object.keys(french).length).toBeLessThan(0.1);
  });
});
