import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router';
import '@/lib/i18n';
import { AppProviders } from '@/app/providers';
import { createAppRouter } from '@/app/router';
import { configurePdfWorker } from '@/features/documents/pdfWorker';
import { initSentry } from '@/lib/sentry';

async function bootstrap() {
  initSentry(); // avant le rendu : une erreur au démarrage est remontée aussi
  if (import.meta.env.VITE_USE_MOCKS === '1') {
    const { startMockWorker } = await import('@/mocks/browser');
    await startMockWorker();
  }
  configurePdfWorker();
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AppProviders>
        <RouterProvider router={createAppRouter()} />
      </AppProviders>
    </StrictMode>,
  );
}

void bootstrap();
