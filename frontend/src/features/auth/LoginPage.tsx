import { Alert, Box, Button, Card, CardContent, Stack, TextField, Typography } from '@mui/material';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Navigate, useLocation, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useLogin } from '@/api/hooks/useAuth';
import { useAuthStore } from '@/features/auth/authStore';
import { extractErrorMessage } from '@/api/client';

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});
type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const login = useLogin();
  const user = useAuthStore((s) => s.user);
  const access = useAuthStore((s) => s.access);
  const { register, handleSubmit, formState } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  });

  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? '/';
  if (user && access) return <Navigate to={from} replace />;

  const onSubmit = (values: FormValues) => {
    login.mutate(values, { onSuccess: () => navigate(from, { replace: true }) });
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'primary.dark',
        p: 2,
      }}
    >
      <Card sx={{ width: '100%', maxWidth: 420 }}>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h4" color="primary" gutterBottom>
            {t('app.name')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            {t('auth.subtitle')}
          </Typography>
          <form onSubmit={handleSubmit(onSubmit)} noValidate>
            <Stack spacing={2}>
              <TextField
                label={t('auth.email')}
                type="email"
                autoComplete="email"
                autoFocus
                fullWidth
                {...register('email')}
                error={!!formState.errors.email}
                helperText={formState.errors.email ? t('auth.invalidEmail') : undefined}
              />
              <TextField
                label={t('auth.password')}
                type="password"
                autoComplete="current-password"
                fullWidth
                {...register('password')}
                error={!!formState.errors.password}
                helperText={formState.errors.password ? t('app.required') : undefined}
              />
              {login.isError && (
                <Alert severity="error" data-testid="login-error">
                  {login.error && (login.error as { response?: { status?: number } }).response?.status === 401
                    ? t('auth.failed')
                    : extractErrorMessage(login.error, t('auth.failed'))}
                </Alert>
              )}
              <Button type="submit" variant="contained" size="large" disabled={login.isPending}>
                {t('auth.submit')}
              </Button>
            </Stack>
          </form>
        </CardContent>
      </Card>
    </Box>
  );
}
