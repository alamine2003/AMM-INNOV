import { Box, Button, Card, CardContent, Stack, Typography } from '@mui/material';
import { Link } from 'react-router';
import { useActionPlan } from '@/api/hooks/useAmms';

/** Plan d'action en bref sur le Dashboard : ce qu'il reste à compléter, un clic pour agir. */
export function ActionPlanCard({ country }: { country?: string }) {
  const plan = useActionPlan({ country, limit: 1 });
  if (!plan.data || plan.data.total === 0) return null;
  const to = `/plan-action${country ? `?country=${country}` : ''}`;
  return (
    <Card variant="outlined" sx={{ mb: 3 }} data-testid="action-plan-card">
      <CardContent>
        <Stack direction={{ xs: 'column', md: 'row' }} gap={2} alignItems={{ md: 'center' }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6">Plan d'action</Typography>
            <Typography variant="body2" color="text.secondary">
              {plan.data.total} AMM à compléter, les plus urgentes d'abord.
            </Typography>
          </Box>
          <Stack direction="row" gap={3} flexWrap="wrap">
            {plan.data.categories
              .filter((category) => category.count > 0)
              .map((category) => (
                <Box
                  key={category.gap}
                  component={Link}
                  to={`${to}#${category.gap}`}
                  sx={{ textDecoration: 'none', color: 'inherit' }}
                >
                  <Typography variant="h6" color="warning.main" sx={{ lineHeight: 1.1 }}>
                    {category.count}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {category.label}
                  </Typography>
                </Box>
              ))}
          </Stack>
          <Button variant="contained" component={Link} to={to}>
            Agir
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
