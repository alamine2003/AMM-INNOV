import {
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  Grid2 as Grid,
  Link as MuiLink,
  List,
  ListItem,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import { Link, useSearchParams } from 'react-router';
import { useActionPlan } from '@/api/hooks/useAmms';
import { useCountries } from '@/api/hooks/useCatalog';
import type { ActionPlanCategory, ActionPlanItem, AmmStatus } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { StatusChip } from '@/components/chips';
import { useAuthStore } from '@/features/auth/authStore';
import { formatDate } from '@/lib/dates';

/** Où agir pour chaque manque : l'onglet de la fiche qui le corrige. */
const TAB: Record<string, string> = {
  no_original: 'detail',
  missing_renewal: 'renewals',
  to_file: 'renewals',
  original_scan: 'documents',
  renewal_scan: 'documents',
};

/** Couleur du manque : ce qui bloque le suivi réglementaire d'abord. */
const TONE: Record<string, 'error' | 'warning' | 'info'> = {
  no_original: 'error',
  missing_renewal: 'error',
  to_file: 'warning',
  original_scan: 'info',
  renewal_scan: 'info',
};

function Item({ item, category }: { item: ActionPlanItem; category: ActionPlanCategory }) {
  return (
    <ListItem
      disableGutters
      divider
      sx={{ gap: 1, flexWrap: { xs: 'wrap', sm: 'nowrap' }, alignItems: 'center' }}
      data-testid={`plan-item-${category.gap}`}
    >
      <Box sx={{ flex: 1, minWidth: 0, flexBasis: { xs: '100%', sm: 0 } }}>
        <MuiLink component={Link} to={`/amms/${item.id}`} underline="hover" fontWeight={600} noWrap>
          {item.product_name}
        </MuiLink>
        <Typography variant="caption" color="text.secondary" component="div">
          {item.country_name}
          {item.original_number ? ` · N° ${item.original_number}` : ''}
          {item.effective_end_date ? ` · échéance ${formatDate(item.effective_end_date)}` : ''}
        </Typography>
      </Box>
      <StatusChip value={item.status as AmmStatus} size="small" />
      <Button
        size="small"
        variant="outlined"
        component={Link}
        to={`/amms/${item.id}?tab=${TAB[category.gap] ?? 'detail'}`}
        sx={{ whiteSpace: 'nowrap' }}
      >
        {category.action}
      </Button>
    </ListItem>
  );
}

function CategoryCard({ category, country }: { category: ActionPlanCategory; country: string }) {
  const list = `/amms?gap=${category.gap}${country ? `&country=${country}` : ''}`;
  return (
    <Card variant="outlined" sx={{ display: 'flex', flexDirection: 'column' }} id={category.gap}>
      <CardContent sx={{ flex: 1, pb: 1 }}>
        <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 0.5 }}>
          <Typography variant="h6" component="h2" sx={{ flex: 1 }}>
            {category.label}
          </Typography>
          <Chip
            label={category.count}
            color={category.count ? TONE[category.gap] : 'success'}
            size="small"
            data-testid={`plan-count-${category.gap}`}
          />
        </Stack>
        <Typography variant="body2" color="text.secondary">
          {category.hint}
        </Typography>
        {category.count === 0 ? (
          <Stack direction="row" alignItems="center" gap={1} sx={{ mt: 2, color: 'success.main' }}>
            <CheckCircleOutlineIcon fontSize="small" />
            <Typography variant="body2">Rien à faire ici.</Typography>
          </Stack>
        ) : (
          <List dense sx={{ mt: 1 }}>
            {category.items.map((item) => (
              <Item key={item.id} item={item} category={category} />
            ))}
          </List>
        )}
      </CardContent>
      {category.count > category.items.length && (
        <CardActions sx={{ pt: 0, px: 2, pb: 1.5 }}>
          <Button size="small" component={Link} to={list}>
            Voir les {category.count} dans la liste des AMM
          </Button>
        </CardActions>
      )}
    </Card>
  );
}

/**
 * Plan d'action : les AMM à compléter, regroupées par manque (origine non identifiée, sans
 * renouvellement, dépôt à lancer, scans absents), les plus urgentes d'abord (expirées, puis à
 * renouveler, puis valides, échéance la plus proche devant). Chaque ligne mène à l'onglet de la
 * fiche qui corrige le manque.
 */
export default function ActionPlanPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const country = searchParams.get('country') ?? '';
  const plan = useActionPlan({ country: country || undefined, limit: 8 });
  const countries = useCountries();
  const user = useAuthStore((s) => s.user);
  const visible = (countries.data ?? []).filter(
    (c) => user?.role !== 'COUNTRY_REGULATORY' || user.countries.includes(c.iso2),
  );

  return (
    <Box>
      <PageHeader
        title="Plan d'action"
        subtitle="Les AMM à compléter, les plus urgentes d'abord : un clic mène à l'endroit où agir."
        actions={
          <TextField
            select
            size="small"
            label="Pays"
            value={country}
            onChange={(event) => setSearchParams(event.target.value ? { country: event.target.value } : {})}
            sx={{ minWidth: 180 }}
            SelectProps={{ displayEmpty: true }}
            InputLabelProps={{ shrink: true }}
            inputProps={{ 'data-testid': 'plan-country' }}
          >
            <MenuItem value="">Tous les pays</MenuItem>
            {visible.map((c) => (
              <MenuItem key={c.iso2} value={c.iso2}>
                {c.name}
              </MenuItem>
            ))}
          </TextField>
        }
      />
      {plan.isPending && <LoadingBlock />}
      {plan.isError && <ErrorBlock error={plan.error} onRetry={() => plan.refetch()} />}
      {plan.data && (
        <>
          <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mb: 2 }} data-testid="plan-summary">
            <Typography variant="body2" color="text.secondary" sx={{ alignSelf: 'center', mr: 1 }}>
              {plan.data.total ? `${plan.data.total} AMM à compléter` : 'Toutes les fiches sont complètes.'}
            </Typography>
            {plan.data.categories
              .filter((category) => category.count > 0)
              .map((category) => (
                <Chip
                  key={category.gap}
                  component="a"
                  href={`#${category.gap}`}
                  clickable
                  variant="outlined"
                  color={TONE[category.gap]}
                  label={`${category.label} : ${category.count}`}
                />
              ))}
          </Stack>
          <Grid container spacing={2} alignItems="flex-start">
            {plan.data.categories.map((category) => (
              <Grid key={category.gap} size={{ xs: 12, lg: 6 }}>
                <CategoryCard category={category} country={country} />
              </Grid>
            ))}
          </Grid>
        </>
      )}
    </Box>
  );
}
