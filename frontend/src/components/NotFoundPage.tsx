import { Box, Button, Typography } from '@mui/material';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <Box sx={{ textAlign: 'center', py: 8 }}>
      <Typography variant="h4" gutterBottom>
        404
      </Typography>
      <Typography color="text.secondary" gutterBottom>
        {t('app.notFound')}
      </Typography>
      <Button component={Link} to="/" variant="contained">
        {t('app.backHome')}
      </Button>
    </Box>
  );
}
