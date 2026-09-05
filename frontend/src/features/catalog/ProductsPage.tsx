import { useState } from 'react';
import { Alert, Box, Button, Chip, Link as MuiLink, Paper, TextField } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { Link, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useProductDuplicates, useProducts } from '@/api/hooks/useCatalog';
import { DuplicatesDialog } from './DuplicatesDialog';
import type { Product } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { isAdmin, isHqOrAdmin, useAuthStore } from '@/features/auth/authStore';
import { ProductFormDialog } from './ProductFormDialog';

export default function ProductsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [search, setSearch] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const products = useProducts(search ? { search } : {});
  const duplicates = useProductDuplicates(isHqOrAdmin(user));
  const [duplicatesOpen, setDuplicatesOpen] = useState(false);

  const columns: GridColDef<Product>[] = [
    {
      field: 'name',
      headerName: t('products.name'),
      flex: 1,
      minWidth: 260,
      renderCell: (p) => (
        <MuiLink component={Link} to={`/products/${p.row.id}`} underline="hover" fontWeight={600}>
          {p.row.name}
        </MuiLink>
      ),
    },
    { field: 'range_code', headerName: t('products.range'), width: 120 },
    { field: 'dci', headerName: t('products.dci'), width: 160 },
    { field: 'dosage', headerName: t('products.dosage'), width: 100 },
    { field: 'form', headerName: t('products.form'), width: 120 },
    { field: 'presentation', headerName: t('products.presentation'), width: 120 },
    {
      field: 'aliases',
      headerName: t('products.aliases'),
      width: 220,
      valueGetter: (_v, row) => row.aliases.join(', '),
    },
    {
      field: 'is_active',
      headerName: t('products.active'),
      width: 90,
      renderCell: (p) => (
        <Chip
          size="small"
          label={p.row.is_active ? t('app.yes') : t('app.no')}
          color={p.row.is_active ? 'success' : 'default'}
        />
      ),
    },
  ];

  return (
    <Box>
      <PageHeader
        title={t('products.title')}
        actions={
          isHqOrAdmin(user) && (
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
              {t('products.create')}
            </Button>
          )
        }
      />
      {(duplicates.data?.length ?? 0) > 0 && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => setDuplicatesOpen(true)}>
              {t('products.duplicates.review')}
            </Button>
          }
        >
          {t('products.duplicates.banner', { count: duplicates.data?.length ?? 0 })}
        </Alert>
      )}
      <TextField
        size="small"
        label={t('app.search')}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 2, minWidth: 280 }}
      />
      <Paper variant="outlined" sx={{ height: 'calc(100vh - 260px)', minHeight: 400 }}>
        <DataGrid
          rows={products.data ?? []}
          columns={columns}
          loading={products.isPending}
          density="compact"
          disableRowSelectionOnClick
          onRowDoubleClick={(p) => navigate(`/products/${p.row.id}`)}
          sx={{ border: 0 }}
        />
      </Paper>
      <ProductFormDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      <DuplicatesDialog
        open={duplicatesOpen}
        onClose={() => setDuplicatesOpen(false)}
        groups={duplicates.data ?? []}
        canMerge={isAdmin(user)}
      />
    </Box>
  );
}
