import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { RequireRole } from '@/app/guards';
import { loginAs, renderWithProviders } from '@/test/utils';

function Page() {
  return <div data-testid="protected">Zone admin</div>;
}

describe('RequireRole', () => {
  it('refuse l’accès à un réglementaire pays', async () => {
    loginAs('u-sn');
    renderWithProviders(
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route element={<RequireRole roles={['CEO_ADMIN', 'HQ_REGULATORY']} />}>
            <Route path="/admin" element={<Page />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('forbidden')).toBeInTheDocument();
    expect(screen.queryByTestId('protected')).not.toBeInTheDocument();
  });

  it('autorise le réglementaire siège', async () => {
    loginAs('u-hq');
    renderWithProviders(
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route element={<RequireRole roles={['CEO_ADMIN', 'HQ_REGULATORY']} />}>
            <Route path="/admin" element={<Page />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('protected')).toBeInTheDocument();
  });

  it('redirige vers /login sans session', async () => {
    renderWithProviders(
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route path="/login" element={<div data-testid="login">login</div>} />
          <Route element={<RequireRole roles={['CEO_ADMIN']} />}>
            <Route path="/admin" element={<Page />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('login')).toBeInTheDocument();
  });
});
