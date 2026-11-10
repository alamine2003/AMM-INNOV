import { afterEach, describe, expect, it, vi } from 'vitest';
import { printBlob } from '../print';

// Le `URL` de Node (Vitest 5) refuse les Blob de jsdom : les adresses blob: sont simulées.
function stubObjectUrls() {
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:scan');
  vi.spyOn(URL, 'revokeObjectURL').mockReturnValue(undefined);
}

describe('impression d’un scan', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.querySelectorAll('iframe').forEach((frame) => frame.remove());
  });

  it('charge le PDF dans un cadre invisible et ouvre l’impression sur lui seul', async () => {
    const print = vi.fn();
    vi.spyOn(HTMLIFrameElement.prototype, 'contentWindow', 'get').mockReturnValue({
      focus: vi.fn(),
      print,
    } as unknown as Window);
    stubObjectUrls();
    const done = printBlob(new Blob(['%PDF-1.4'], { type: 'application/pdf' }), 'Décision');
    const frame = document.querySelector('iframe');
    expect(frame).not.toBeNull();
    expect(frame!.style.opacity).toBe('0');
    frame!.dispatchEvent(new Event('load'));
    await done;
    expect(print).toHaveBeenCalledTimes(1);
  });

  it('ouvre le scan dans un onglet si le navigateur refuse d’imprimer le cadre', async () => {
    vi.spyOn(HTMLIFrameElement.prototype, 'contentWindow', 'get').mockReturnValue({
      focus: vi.fn(),
      print: () => {
        throw new Error('bloqué');
      },
    } as unknown as Window);
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    stubObjectUrls();
    const done = printBlob(new Blob(['%PDF-1.4'], { type: 'application/pdf' }));
    document.querySelector('iframe')!.dispatchEvent(new Event('load'));
    await expect(done).rejects.toThrow('bloqué');
    expect(open).toHaveBeenCalledWith(expect.stringMatching(/^blob:/), '_blank', 'noopener');
  });
});
