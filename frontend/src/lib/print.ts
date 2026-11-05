/**
 * Imprime un scan (PDF ou image) sans quitter la page : le fichier est chargé dans un cadre
 * invisible, puis la boîte d'impression du navigateur s'ouvre sur lui seul.
 */
export function printBlob(blob: Blob, title = 'Document'): Promise<void> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const frame = document.createElement('iframe');
    frame.setAttribute('aria-hidden', 'true');
    frame.title = title;
    // Hors de l'écran mais rendu : un cadre `display: none` ne s'imprime pas dans Chrome.
    Object.assign(frame.style, {
      position: 'fixed',
      right: '0',
      bottom: '0',
      width: '1px',
      height: '1px',
      border: '0',
      opacity: '0',
    });
    const cleanup = () => {
      // Laisser la boîte d'impression lire le fichier avant de le libérer.
      setTimeout(() => {
        frame.remove();
        URL.revokeObjectURL(url);
      }, 60_000);
    };
    const print = () => {
      try {
        frame.contentWindow?.focus();
        frame.contentWindow?.print();
        resolve();
      } catch (error) {
        // Navigateur qui refuse d'imprimer un cadre : le scan s'ouvre dans un onglet, à imprimer.
        window.open(url, '_blank', 'noopener');
        reject(error instanceof Error ? error : new Error(String(error)));
      } finally {
        cleanup();
      }
    };
    if (blob.type.startsWith('image/')) {
      // Une image seule : une page HTML qui la tient sur une feuille A4.
      frame.srcdoc =
        `<!doctype html><html><head><title>${title.replace(/[<>&"]/g, '')}</title>` +
        '<style>@page{margin:10mm}html,body{margin:0}img{display:block;max-width:100%;' +
        'max-height:277mm;margin:0 auto}</style></head><body>' +
        `<img src="${url}" alt=""></body></html>`;
      frame.onload = () => {
        const image = frame.contentDocument?.querySelector('img');
        if (image && !image.complete) image.onload = print;
        else print();
      };
    } else {
      frame.src = url;
      // Le lecteur PDF du navigateur a besoin d'un instant après le chargement.
      frame.onload = () => setTimeout(print, 300);
    }
    document.body.appendChild(frame);
  });
}
