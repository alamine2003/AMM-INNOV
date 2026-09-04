import { useState } from 'react';
import { Box, Button, Chip, Link as MuiLink, Paper, TextField } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { Link, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useProducts } from '@/api/hooks/useCatalog';
import type { Product } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { isHqOrAdmin, useAuthStore } from '@/features/auth/authStore';
import { ProductFormDialog } from './ProductFormDialog';

export default function ProductsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [search, setSearch] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const products = useProducts(search ? { search } : {});

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
    </Box>
  );
}
