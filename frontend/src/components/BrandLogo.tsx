import { Box, Stack, Typography, type TypographyProps } from '@mui/material';
import { useTranslation } from 'react-i18next';
import logo from '@/assets/logo-gh.png';

/**
 * Marque de l'application : logo Generic Healthcare et nom « AMM GH ». Les filiales pays
 * travaillent sous la marque GH ; INNOV est le siège.
 */
export function BrandLogo({
  size = 32,
  variant = 'h6',
}: {
  size?: number;
  variant?: TypographyProps['variant'];
}) {
  const { t } = useTranslation();
  return (
    <Stack direction="row" alignItems="center" spacing={1.25}>
      <Box component="img" src={logo} alt="Generic Healthcare" sx={{ height: size, width: 'auto' }} />
      <Typography variant={variant} color="primary" sx={{ fontWeight: 800 }}>
        {t('app.name')}
      </Typography>
    </Stack>
  );
}
