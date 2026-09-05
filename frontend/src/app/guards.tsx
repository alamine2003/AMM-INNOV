import type { ReactNode } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router';
import { Alert, Box, Button, CircularProgress } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/features/auth/authStore';
import { useMe } from '@/api/hooks/useAuth';
import { refreshAccessToken } from '@/api/client';
import { useEffect } from 'react';
import type { Role } from '@/api/types';

/** Restaure la session à partir du refresh token, puis charge /me. */
export function RequireAuth({ children }: { children?: ReactNode }) {
  const location = useLocation();
  const { access, refresh, user, hydrated } = useAuthStore();
  // Dérivé du store plutôt que d'un état local : un refresh réussi pose `access`, un refresh
  // en échec efface `refresh` (logout). Un état local + drapeau `cancelled` restait bloqué à
  // `true` car la mise à jour d'`access` démontait l'effet avant son `finally`.
  const restoring = !access && !!refresh;

  useEffect(() => {
    if (access || !refresh) return;
    void refreshAccessToken();
  }, [access, refresh]);

  const meQuery = useMe(!!access && !user);

  if (restoring || (access && !user && meQuery.isPending)) {
    return (
      <Box
        sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}
        data-testid="auth-loading"
      >
        <CircularProgress />
      </Box>
    );
  }

  if (!access || (!user && !hydrated && meQuery.isError)) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return children ? <>{children}</> : <Outlet />;
}

export function RequireRole({ roles, children }: { roles: Role[]; children?: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const { t } = useTranslation();
  if (!user) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role)) {
    return (
      <Box sx={{ p: 4 }}>
        <Alert
          severity="error"
          data-testid="forbidden"
          action={
            <Button color="inherit" href="/">
              {t('app.backHome')}
            </Button>
          }
        >
          {t('app.forbidden')}
        </Alert>
      </Box>
    );
  }
  return children ? <>{children}</> : <Outlet />;
}
