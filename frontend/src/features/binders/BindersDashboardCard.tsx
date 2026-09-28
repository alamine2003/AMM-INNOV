import { Box, Button, Card, CardContent, LinearProgress, Stack, Typography } from '@mui/material';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import { Link } from 'react-router';
import { useBinders } from '@/api/hooks/useBinders';

/** Avancement des classeurs papier sur le Dashboard : la vérification fait partie du suivi. */
export function BindersDashboardCard() {
  const shelf = useBinders();
  if (!shelf.data?.length) return null;
  const sum = (key: 'total' | 'checked' | 'absent' | 'to_scan' | 'corrected' | 'extras') =>
    shelf.data.reduce((acc, binder) => acc + binder[key], 0);
  const total = sum('total');
  const checked = sum('checked');
  const open = shelf.data.filter((binder) => binder.readers.length > 0);
  const figures = [
    { label: 'corrigées', value: sum('corrected'), color: '#e65100' },
    { label: 'dossiers absents', value: sum('absent'), color: '#c62828' },
    { label: 'décisions à scanner', value: sum('to_scan'), color: '#c62828' },
    { label: 'pages en trop', value: sum('extras'), color: '#6b7280' },
  ];
  return (
    <Card variant="outlined" sx={{ mb: 3 }} data-testid="binders-dashboard">
      <CardContent>
        <Stack direction={{ xs: 'column', md: 'row' }} gap={2} alignItems={{ md: 'center' }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6">Classeurs papier</Typography>
            <Typography variant="body2" color="text.secondary">
              {checked} / {total} pages vérifiées sur le papier
              {open.length > 0 &&
                ` · ouverts en ce moment : ${open.map((b) => `${b.country_name} ${b.title} (${b.readers.join(', ')})`).join(' ; ')}`}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={total ? (checked / total) * 100 : 0}
              color="success"
              sx={{ mt: 1, height: 8, borderRadius: 4 }}
              aria-label="Avancement des classeurs"
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
            Ouvrir les classeurs
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
