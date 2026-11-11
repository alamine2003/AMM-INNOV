import { afterEach, describe, expect, it, vi } from 'vitest';
import { isStaleChunkError, reloadForNewVersion } from '@/lib/staleChunks';

describe('fichiers de l’ancienne version après un déploiement', () => {
  afterEach(() => {
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it('reconnaît les messages des navigateurs', () => {
    expect(
      isStaleChunkError(
        new TypeError(
          "'text/html' is not a valid JavaScript MIME type for module script 'https://amm-gh.pages.dev/assets/AlertsPage-BZr8fdgj.js'.",
        ),
      ),
    ).toBe(true);
    expect(isStaleChunkError(new TypeError('Failed to fetch dynamically imported module: /a.js'))).toBe(true);
    expect(isStaleChunkError(new TypeError('Importing a module script failed.'))).toBe(true);
    expect(isStaleChunkError(new Error('Request failed with status code 500'))).toBe(false);
  });

  it('recharge une seule fois par minute', () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, reload });
    expect(reloadForNewVersion(1_000_000)).toBe(true);
    expect(reloadForNewVersion(1_030_000)).toBe(false);
    expect(reloadForNewVersion(1_070_000)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });
});
