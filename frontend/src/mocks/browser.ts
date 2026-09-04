import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

export const worker = setupWorker(...handlers);

export async function startMockWorker() {
  await worker.start({ onUnhandledRequest: 'bypass', serviceWorker: { url: '/mockServiceWorker.js' } });
  console.info(
    '[MSW] Mocks actifs — comptes : ceo@amm-innov.test / siege@amm-innov.test / senegal@amm-innov.test, mot de passe Passw0rd!',
  );
}
