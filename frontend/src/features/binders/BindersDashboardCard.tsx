import { Box, Button, Card, CardContent, LinearProgress, Stack, Typography } from '@mui/material';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { useBinders } from '@/api/hooks/useBinders';

/** Avancement des classeurs papier sur le Dashboard : la vérification fait partie du suivi. */
export function BindersDashboardCard() {
  const { t } = useTranslation();
  const shelf = useBinders();
  if (!shelf.data?.length) return null;
  const sum = (
    key:
      | 'total'
      | 'checked'
      | 'conformes'
      | 'non_conformes'
      | 'absent'
      | 'to_scan'
      | 'to_print'
      | 'corrected'
      | 'extras',
  ) => shelf.data.reduce((acc, binder) => acc + binder[key], 0);
  const total = sum('total');
  const checked = sum('checked');
  const open = shelf.data.filter((binder) => binder.readers.length > 0);
  const figures = [
    { label: t('binders.dashboard.conform'), value: sum('conformes'), color: '#2e7d32' },
    { label: t('binders.dashboard.nonConform'), value: sum('non_conformes'), color: '#e65100' },
    { label: t('binders.dashboard.absent'), value: sum('absent'), color: '#c62828' },
    { label: t('binders.dashboard.toScan'), value: sum('to_scan'), color: '#c62828' },
    { label: t('binders.dashboard.toPrint'), value: sum('to_print'), color: '#1565c0' },
    { label: t('binders.dashboard.extras'), value: sum('extras'), color: '#6b7280' },
  ];
  return (
    <Card variant="outlined" sx={{ mb: 3 }} data-testid="binders-dashboard">
      <CardContent>
        <Stack direction={{ xs: 'column', md: 'row' }} gap={2} alignItems={{ md: 'center' }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6">{t('binders.dashboard.title')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('binders.dashboard.progress', { checked, total })}
              {open.length > 0 &&
                ` · ${t('binders.dashboard.openNow', {
                  list: open.map((b) => `${b.country_name} ${b.title} (${b.readers.join(', ')})`).join(' ; '),
                })}`}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={total ? (checked / total) * 100 : 0}
              color="success"
              sx={{ mt: 1, height: 8, borderRadius: 4 }}
              aria-label={t('binders.dashboard.progressLabel')}
            />
          </Box>
          <Stack direction="row" gap={3} flexWrap="wrap">
            {figures.map((figure) => (
              <Box key={figure.label}>
                <Typography
                  variant="h6"
                  sx={{ color: figure.value ? figure.color : 'text.secondary', lineHeight: 1.1 }}
                >
                  {figure.value}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {figure.label}
                </Typography>
              </Box>
            ))}
          </Stack>
          <Button component={Link} to="/classeurs" variant="outlined" startIcon={<MenuBookIcon />}>
            {t('binders.dashboard.openBinders')}
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
