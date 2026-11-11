import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RouteError } from '@/app/RouteError';

function Boom({ message }: { message: string }): never {
  throw new TypeError(message);
}

const renderFailing = (message: string) =>
  render(
    <RouterProvider
      router={createMemoryRouter([
        { path: '/', element: <Boom message={message} />, errorElement: <RouteError /> },
      ])}
    />,
  );

describe('RouteError', () => {
  afterEach(() => {
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('affiche un message clair au lieu de l’écran brut', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderFailing('Cannot read properties of undefined');
    expect(await screen.findByTestId('route-error')).toHaveTextContent("Cette page n'a pas pu s'afficher");
  });

  it('recharge seul quand la page vient d’une version remplacée', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const reload = vi.fn();
    vi.stubGlobal('location', { ...window.location, reload });
    renderFailing("'text/html' is not a valid JavaScript MIME type for module script 'x.js'.");
    expect(await screen.findByTestId('route-error-reloading')).toBeInTheDocument();
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
