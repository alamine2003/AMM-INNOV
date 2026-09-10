import '@testing-library/jest-dom/vitest';
import type React from 'react';
import { Blob as NodeBlob, File as NodeFile } from 'node:buffer';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@/lib/i18n';
import { server } from '@/mocks/server';
import { resetDb } from '@/mocks/handlers';
import { useAuthStore } from '@/features/auth/authStore';

// jsdom apporte ses propres FormData/File/Blob, que l'implémentation Fetch de Node (celle que
// MSW utilise pour lire les requêtes) ne reconnaît pas : un envoi multipart y devient le texte
// « [object FormData] ». Vitest injecte déjà Request/Response/fetch de Node dans jsdom ; on
// complète la liste par les trois classes de corps pour que les deux moitiés s'accordent.
const nativeFormData = (
  await new Response('a=1', {
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
  }).formData()
).constructor as typeof FormData;
globalThis.FormData = nativeFormData;
globalThis.File = NodeFile as unknown as typeof File;
globalThis.Blob = NodeBlob as unknown as typeof Blob;

// Polyfills jsdom
if (!globalThis.matchMedia) {
  Object.defineProperty(globalThis, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
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
