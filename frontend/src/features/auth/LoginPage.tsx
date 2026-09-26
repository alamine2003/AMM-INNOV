import { Alert, Box, Button, Stack, TextField, Typography } from '@mui/material';
import type { ReactNode } from 'react';
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined';
import EventAvailableOutlinedIcon from '@mui/icons-material/EventAvailableOutlined';
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Navigate, useLocation, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useLogin } from '@/api/hooks/useAuth';
import { useAuthStore } from '@/features/auth/authStore';
import { extractErrorMessage } from '@/api/client';
import { BrandLogo } from '@/components/BrandLogo';

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
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', lg: '1.1fr 1fr' },
        bgcolor: 'background.default',
      }}
    >
      <Box
        component="aside"
        sx={{
          position: 'relative',
          overflow: 'hidden',
          display: { xs: 'none', lg: 'flex' },
          flexDirection: 'column',
          p: 6,
          bgcolor: BANNER,
          color: BANNER_TEXT,
        }}
      >
        <Circle sx={{ top: -128, right: -128 }} />
        <Circle sx={{ bottom: -160, left: -96 }} />
        <Box sx={{ position: 'relative' }}>
          <BrandLogo height={36} sx={{ color: BANNER_TEXT }} />
          <Typography variant="caption" sx={{ display: 'block', mt: 1, color: BANNER_MUTED }}>
            {t('auth.tagline')}
          </Typography>
        </Box>
        <Box sx={{ position: 'relative', flex: 1, display: 'flex', alignItems: 'center', py: 6 }}>
          <Box sx={{ maxWidth: 460 }}>
            <Typography
              component="h1"
              sx={{ fontSize: 30, fontWeight: 600, lineHeight: 1.25, letterSpacing: -0.4 }}
            >
              {t('auth.headline1')}
              <br />
              {t('auth.headline2')}
            </Typography>
            <Typography variant="body2" sx={{ mt: 2, color: BANNER_MUTED, lineHeight: 1.7 }}>
              {t('auth.intro')}
            </Typography>
            <Stack component="ul" spacing={3} sx={{ mt: 5, p: 0, listStyle: 'none' }}>
              <Feature
                icon={<DescriptionOutlinedIcon fontSize="small" />}
                title={t('auth.feature1Title')}
                text={t('auth.feature1Text')}
              />
              <Feature
                icon={<EventAvailableOutlinedIcon fontSize="small" />}
                title={t('auth.feature2Title')}
                text={t('auth.feature2Text')}
              />
              <Feature
                icon={<AutoAwesomeOutlinedIcon fontSize="small" />}
                title={t('auth.feature3Title')}
                text={t('auth.feature3Text')}
              />
            </Stack>
          </Box>
        </Box>
        <Box sx={{ position: 'relative', color: BANNER_MUTED }}>
          <Typography variant="caption" component="p">
            {t('auth.restricted')}
          </Typography>
          <Typography variant="caption" component="p">
            {t('auth.copyright', { year: new Date().getFullYear() })}
          </Typography>
        </Box>
      </Box>

      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', p: { xs: 3, sm: 6 } }}>
        <Box sx={{ width: '100%', maxWidth: 400 }}>
          <Box sx={{ display: { xs: 'block', lg: 'none' }, mb: 4 }}>
            <BrandLogo height={32} />
          </Box>
          <Typography component="h2" variant="h5" sx={{ fontWeight: 600 }}>
            {t('auth.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 4 }}>
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
        </Box>
      </Box>
    </Box>
  );
}

/** Bannière de connexion : bleu nuit du logo GH, texte clair. */
const BANNER = '#16213d';
const BANNER_TEXT = '#f5f7fb';
const BANNER_MUTED = '#9ba7c2';

function Circle({ sx }: { sx: object }) {
  return (
    <Box
      aria-hidden
      sx={{
        position: 'absolute',
        width: 384,
        height: 384,
        borderRadius: '50%',
        bgcolor: 'rgba(245, 247, 251, 0.05)',
        pointerEvents: 'none',
        ...sx,
      }}
    />
  );
}

function Feature({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return (
    <Stack component="li" direction="row" spacing={2}>
      <Box
        sx={{
          mt: 0.25,
          width: 32,
          height: 32,
          flexShrink: 0,
          borderRadius: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          bgcolor: 'rgba(245, 247, 251, 0.1)',
        }}
      >
        {icon}
      </Box>
      <Box>
        <Typography variant="body2" sx={{ fontWeight: 500 }}>
          {title}
        </Typography>
        <Typography variant="body2" sx={{ mt: 0.25, color: BANNER_MUTED }}>
          {text}
        </Typography>
      </Box>
    </Stack>
  );
}
