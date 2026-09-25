import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const version = (name: string) =>
  (JSON.parse(readFileSync(require.resolve(`${name}/package.json`), 'utf8')) as { version: string }).version;

describe('worker pdf.js', () => {
  it('a exactement la version de pdf.js utilisée par react-pdf', () => {
    // « The API version "5.4.296" does not match the Worker version "5.7.284" » : aucun scan
    // ne s'affichait quand pdfjs-dist (le worker) avait été mis à jour sans react-pdf.
    const reactPdf = JSON.parse(readFileSync(require.resolve('react-pdf/package.json'), 'utf8')) as {
      dependencies: Record<string, string>;
    };
    expect(version('pdfjs-dist')).toBe(reactPdf.dependencies['pdfjs-dist']);
  });
});
