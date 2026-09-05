import { useState } from 'react';
import {
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Grid2 as Grid,
  Link as MuiLink,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import MergeIcon from '@mui/icons-material/CallMerge';
import { Link, useNavigate, useParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import {
  useMergeProduct,
  useProduct,
  useProductCoverage,
  useProductDocuments,
  useProducts,
} from '@/api/hooks/useCatalog';
import { useAmms } from '@/api/hooks/useAmms';
import { PageHeader } from '@/components/PageHeader';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { STATUS_COLORS } from '@/lib/urgency';
import { formatDate } from '@/lib/dates';
import { isAdmin, isHqOrAdmin, useAuthStore } from '@/features/auth/authStore';
import { ProductFormDialog } from './ProductFormDialog';
import { StatusChip, UrgencyChip } from '@/components/chips';
import type { Product } from '@/api/types';

export default function ProductDetailPage() {
  const { id = '' } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const user = useAuthStore((s) => s.user);
  const product = useProduct(id);
  const coverage = useProductCoverage(id);
  const documents = useProductDocuments(id);
  const amms = useAmms({ page_size: 100, search: product.data?.name });
  const products = useProducts();
  const merge = useMergeProduct();
  const [editOpen, setEditOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [target, setTarget] = useState<Product | null>(null);

  if (product.isPending) return <LoadingBlock />;
  if (product.isError) return <ErrorBlock error={product.error} onRetry={() => product.refetch()} />;
  const p = product.data;
  const productAmms = (amms.data?.results ?? []).filter((a) => a.product === p.id);

  return (
    <Box>
      <PageHeader
        title={p.name}
        subtitle={
          <Stack direction="row" spacing={1} sx={{ mt: 0.5 }} flexWrap="wrap" useFlexGap>
            <Chip size="small" label={p.range_code} />
            {p.dci && <Chip size="small" label={`${t('products.dci')} : ${p.dci}`} variant="outlined" />}
            {p.dosage && <Chip size="small" label={p.dosage} variant="outlined" />}
            {p.form && <Chip size="small" label={p.form} variant="outlined" />}
            {p.presentation && <Chip size="small" label={p.presentation} variant="outlined" />}
          </Stack>
        }
        actions={
          <>
            {isHqOrAdmin(user) && (
              <Button variant="outlined" startIcon={<EditIcon />} onClick={() => setEditOpen(true)}>
                {t('app.edit')}
              </Button>
            )}
            {isAdmin(user) && (
              <Button
                variant="outlined"
                color="warning"
                startIcon={<MergeIcon />}
                onClick={() => setMergeOpen(true)}
              >
                {t('products.merge')}
              </Button>
            )}
          </>
        }
      />
      <Grid container spacing={2}>
        <Grid size={12}>
          <Card variant="outlined">
            <CardHeader title={t('products.coverage')} titleTypographyProps={{ variant: 'h6' }} />
            <CardContent>
              {coverage.isPending && <LoadingBlock minHeight={80} />}
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
                  gap: 1.5,
                }}
                data-testid="coverage-grid"
              >
                {(coverage.data ?? []).map((c) => {
                  const color = c.status
                    ? STATUS_COLORS[c.status]
                    : c.in_scope === false
                      ? '#e0e0e0'
                      : '#bdbdbd';
                  const emptyLabel = t(
                    c.in_scope === false ? 'products.coverageOutOfScope' : 'products.coverageAbsent',
                  );
                  const amm = productAmms.find((a) => a.country_iso2 === c.country_iso2);
                  const cell = (
                    <Box
                      sx={{
                        p: 1.5,
                        borderRadius: 1,
                        bgcolor: color,
                        color: '#fff',
                        cursor: amm ? 'pointer' : 'default',
                        minHeight: 72,
                      }}
                      onClick={() => amm && navigate(`/amms/${amm.id}`)}
                      data-testid={`coverage-${c.country_iso2}`}
                    >
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                        {c.country_name}
                      </Typography>
                      <Typography variant="caption" display="block">
                        {c.status ? t(`status.${c.status}`) : emptyLabel}
                      </Typography>
                      {c.effective_end_date && (
                        <Typography variant="caption" display="block">
                          {formatDate(c.effective_end_date)}
                        </Typography>
                      )}
                    </Box>
                  );
                  return (
                    <Tooltip
                      key={c.country_iso2}
                      title={
                        c.status
                          ? `${t(`status.${c.status}`)} — ${formatDate(c.effective_end_date)}`
                          : emptyLabel
                      }
                    >
                      {cell}
                    </Tooltip>
                  );
                })}
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardHeader title={t('nav.amms')} titleTypographyProps={{ variant: 'h6' }} />
            <CardContent sx={{ pt: 0, overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('amm.columns.country')}</TableCell>
                    <TableCell>{t('amm.columns.number')}</TableCell>
                    <TableCell>{t('amm.columns.status')}</TableCell>
                    <TableCell>{t('amm.columns.urgency')}</TableCell>
                    <TableCell>{t('amm.columns.effectiveEnd')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {productAmms.map((a) => (
                    <TableRow key={a.id} hover>
                      <TableCell>
                        <MuiLink component={Link} to={`/amms/${a.id}`} underline="hover">
                          {a.country_name}
                        </MuiLink>
                      </TableCell>
                      <TableCell>{a.current_renewal?.number ?? a.original_number ?? '—'}</TableCell>
                      <TableCell>
                        <StatusChip value={a.status} />
                      </TableCell>
                      <TableCell>
                        <UrgencyChip value={a.urgency} />
                      </TableCell>
                      <TableCell>{formatDate(a.effective_end_date)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardHeader title={t('products.documents')} titleTypographyProps={{ variant: 'h6' }} />
            <CardContent sx={{ pt: 0 }}>
              {(documents.data ?? []).length === 0 && (
                <Typography color="text.secondary">{t('documents.empty')}</Typography>
              )}
              <Stack spacing={1}>
                {(documents.data ?? []).map((d) => (
                  <Box key={d.id} sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                    <MuiLink component={Link} to={`/amms/${d.amm_id}?tab=documents`} underline="hover" noWrap>
                      {d.country_iso2} — {d.title}
                    </MuiLink>
                    <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                      {t(`documentKind.${d.kind}`)} · {formatDate(d.document_date)}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        {p.aliases.length > 0 && (
          <Grid size={12}>
            <Typography variant="subtitle2">{t('products.aliases')}</Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
              {p.aliases.map((a) => (
                <Chip key={a} size="small" label={a} variant="outlined" />
              ))}
            </Stack>
          </Grid>
        )}
      </Grid>
      <ProductFormDialog open={editOpen} onClose={() => setEditOpen(false)} product={p} />
      <Dialog open={mergeOpen} onClose={() => setMergeOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('products.mergeTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>{t('products.mergeHelp')}</DialogContentText>
          <Autocomplete
            options={(products.data ?? []).filter((x) => x.id !== p.id)}
            getOptionLabel={(x) => x.name}
            value={target}
            onChange={(_e, v) => setTarget(v)}
            renderInput={(params) => <TextField {...params} label={t('products.mergeTarget')} />}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMergeOpen(false)}>{t('app.cancel')}</Button>
          <Button
            variant="contained"
            color="warning"
            disabled={!target || merge.isPending}
            onClick={() =>
              target &&
              merge.mutate(
                { id: p.id, target_id: target.id },
                {
                  onSuccess: () => {
                    enqueueSnackbar(t('products.merged'), { variant: 'success' });
                    navigate(`/products/${target.id}`);
                  },
                },
              )
            }
          >
            {t('app.confirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
