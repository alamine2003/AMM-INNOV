import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router';
import { Alert, Box, Button, CircularProgress } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { can, useAuthStore } from '@/features/auth/authStore';
import { useMe } from '@/api/hooks/useAuth';
import { refreshAccessToken } from '@/api/client';
import type { Role, UserAction } from '@/api/types';

/**
 * Restaure la session au chargement : un rafraîchissement silencieux avec le cookie httpOnly,
 * puis /me. Sans cookie valide, l'API répond 401 et l'utilisateur est renvoyé à la connexion.
 */
export function RequireAuth({ children }: { children?: ReactNode }) {
  const location = useLocation();
  const { access, user, sessionChecked } = useAuthStore();
  const restoring = !access && !sessionChecked;

  useEffect(() => {
    if (!restoring) return;
    void refreshAccessToken().finally(() => useAuthStore.getState().markSessionChecked());
  }, [restoring]);

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

  if (!access || !user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return children ? <>{children}</> : <Outlet />;
}

export function RequireRole({ roles, children }: { roles: Role[]; children?: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/login" replace />;
  return <Allowed ok={roles.includes(user.role)}>{children}</Allowed>;
}

/** Page réservée à une action réglable par le CEO (Administration › Permissions). */
export function RequireAction({ action, children }: { action: UserAction; children?: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/login" replace />;
  return <Allowed ok={can(user, action)}>{children}</Allowed>;
}

function Allowed({ ok, children }: { ok: boolean; children?: ReactNode }) {
  const { t } = useTranslation();
  if (!ok) {
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
