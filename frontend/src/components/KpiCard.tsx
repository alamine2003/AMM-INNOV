import { Card, CardContent, Typography } from '@mui/material';

export function KpiCard({
  label,
  value,
  color,
  hint,
}: {
  label: string;
  value: string | number;
  color?: string;
  hint?: string;
}) {
  return (
    <Card variant="outlined" sx={{ height: '100%', borderTop: 4, borderTopColor: color ?? 'primary.main' }}>
      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}
        >
          {label}
        </Typography>
        <Typography
          variant="h5"
          sx={{ fontWeight: 700, color: color ?? 'text.primary' }}
          data-testid={`kpi-${label}`}
        >
          {value}
        </Typography>
        {hint && (
          <Typography variant="caption" color="text.secondary">
            {hint}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
