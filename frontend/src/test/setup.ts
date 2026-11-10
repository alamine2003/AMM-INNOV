import '@testing-library/jest-dom/vitest';
import type React from 'react';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';
import { cleanup, configure } from '@testing-library/react';
import '@/lib/i18n';
import { server } from '@/mocks/server';
import { resetDb } from '@/mocks/handlers';
import { useAuthStore } from '@/features/auth/authStore';

// Vitest 5 + jsdom 31 : FormData, File et Blob de jsdom sont lus directement par MSW. Seule
// lacune : MSW rend une réponse binaire (scan, PDF) en `Blob` jsdom, que le `Response` de Node
// lit par `stream()`, absent chez jsdom. On l'ajoute.
if (typeof Blob.prototype.stream !== 'function') {
  Blob.prototype.stream = function stream(this: Blob) {
    return new ReadableStream<Uint8Array>({
      start: async (controller) => {
        controller.enqueue(new Uint8Array(await this.arrayBuffer()));
        controller.close();
      },
    });
  } as Blob['stream'];
}

// Le premier rendu d'une page charge ses modules (sélecteur de date…) : 1 s ne suffit pas en CI.
configure({ asyncUtilTimeout: 4000 });

// Polyfills jsdom
if (!globalThis.matchMedia) {
  Object.defineProperty(globalThis, 'matchMedia', {
    writable: true,
    // Souris (« pointer: fine ») : les sélecteurs de date s'ouvrent en mode bureau, saisissables.
    value: (query: string) => ({
      matches: query.includes('pointer: fine'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
if (!URL.createObjectURL) {
  URL.createObjectURL = () => 'blob:mock';
  URL.revokeObjectURL = () => {};
}
// Pas de WebSocket réel dans les tests : le hook passe en polling.
Object.defineProperty(globalThis, 'WebSocket', { value: undefined, writable: true, configurable: true });

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  resetDb();
  useAuthStore.getState().logout();
  localStorage.clear();
  cleanup();
});
afterAll(() => server.close());

// pdf.js exige DOMMatrix/canvas, absents de jsdom : on remplace react-pdf par des stubs.
vi.mock('react-pdf', () => ({
  pdfjs: { GlobalWorkerOptions: { workerSrc: '' } },
  Document: ({ children }: { children?: React.ReactNode }) => children ?? null,
  Page: () => null,
}));
vi.mock('react-pdf/dist/Page/AnnotationLayer.css', () => ({}));
vi.mock('react-pdf/dist/Page/TextLayer.css', () => ({}));
