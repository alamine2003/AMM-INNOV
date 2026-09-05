import { useMemo, useState } from 'react';
import { Box, Button, IconButton, Link as MuiLink, Paper, Tooltip } from '@mui/material';
import { DataGrid, type GridColDef, type GridRowModel, type GridSortModel } from '@mui/x-data-grid';
import AddIcon from '@mui/icons-material/Add';
import DownloadIcon from '@mui/icons-material/Download';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { exportAmms, useAmms, useUpdateAmm } from '@/api/hooks/useAmms';
import type { Amm, AmmFilters as Filters, DossierState } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { StatusChip, UrgencyChip } from '@/components/chips';
import { formatDate, parseDisplayDate } from '@/lib/dates';
import { DOSSIER_STATES } from '@/lib/urgency';
import { saveBlob } from '@/lib/download';
import { extractErrorMessage } from '@/api/client';
import { canEditCountry, useAuthStore } from '@/features/auth/authStore';
import { AmmFilters } from './AmmFilters';
import { AmmCreateDialog } from './AmmCreateDialog';

const FILTER_KEYS: (keyof Filters)[] = [
  'country',
  'range',
  'status',
  'urgency',
  'dossier_state',
  'expires_before',
  'has_current_scan',
  'search',
  'ordering',
];

function readFilters(sp: URLSearchParams): Filters {
  const f: Filters = {};
  for (const k of FILTER_KEYS) {
    const v = sp.get(k);
    if (v) (f as Record<string, unknown>)[k] = v;
  }
  const page = sp.get('page');
  if (page) f.page = Number(page);
  return f;
}

export default function AmmListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => readFilters(searchParams), [searchParams]);
  const [pageSize, setPageSize] = useState(25);
  const [createOpen, setCreateOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const user = useAuthStore((s) => s.user);

  const query = useAmms({
    ...filters,
    page: filters.page ?? 1,
    page_size: pageSize,
    ordering: filters.ordering ?? 'effective_end_date',
  });
  const update = useUpdateAmm();

  const setFilters = (next: Filters) => {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(next))
      if (v !== undefined && v !== '' && v !== null) sp.set(k, String(v));
    setSearchParams(sp);
  };

  const processRowUpdate = async (newRow: GridRowModel<Amm>, oldRow: GridRowModel<Amm>) => {
    const patch: Record<string, unknown> = {};
    if (newRow.original_number !== oldRow.original_number) patch.original_number = newRow.original_number;
    if (newRow.original_start_date !== oldRow.original_start_date)
      patch.original_start_date = newRow.original_start_date;
    if (newRow.original_end_date !== oldRow.original_end_date) {
      patch.original_end_date = newRow.original_end_date;
      patch.original_end_date_manual = true;
    }
    if (newRow.dossier_state !== oldRow.dossier_state) patch.dossier_state = newRow.dossier_state;
    if (Object.keys(patch).length === 0) return oldRow;
    try {
      const saved = await update.mutateAsync({ id: newRow.id, ...(patch as Partial<Amm>) });
      enqueueSnackbar(t('amm.updated'), { variant: 'success' });
      return saved;
    } catch (err) {
      enqueueSnackbar(`${t('amm.updateFailed')} — ${extractErrorMessage(err)}`, { variant: 'error' });
      return oldRow;
    }
  };

  const dateColumn = (field: keyof Amm, header: string, editable: boolean): GridColDef<Amm> => ({
    field,
    headerName: header,
    width: 120,
    editable,
    valueFormatter: (value: string | null) => formatDate(value),
    valueParser: (value: string) => (value?.includes('/') ? parseDisplayDate(value) : value || null),
    type: 'string',
  });

  const columns: GridColDef<Amm>[] = [
    {
      field: 'country_iso2',
      headerName: t('amm.columns.country'),
      width: 80,
      valueGetter: (_v, row) => row.country_iso2,
      renderCell: (p) => (
        <Tooltip title={p.row.country_name}>
          <span>{p.row.country_iso2}</span>
        </Tooltip>
      ),
    },
    { field: 'range_code', headerName: t('amm.columns.range'), width: 110 },
    {
      field: 'product_name',
      headerName: t('amm.columns.product'),
      flex: 1,
      minWidth: 220,
      renderCell: (p) => (
        <MuiLink component={Link} to={`/amms/${p.row.id}`} underline="hover" fontWeight={600}>
          {p.row.product_name}
        </MuiLink>
      ),
    },
    { field: 'original_number', headerName: t('amm.columns.number'), width: 140, editable: true },
    dateColumn('original_start_date', t('amm.columns.startDate'), true),
    dateColumn('original_end_date', t('amm.columns.endDate'), true),
    {
      field: 'renewal_number',
      headerName: t('amm.columns.renewalNumber'),
      width: 150,
      valueGetter: (_v, row) => row.last_renewal?.number ?? '',
    },
    {
      field: 'renewal_start',
      headerName: t('amm.columns.renewalStart'),
      width: 120,
      valueGetter: (_v, row) => row.last_renewal?.start_date ?? null,
      valueFormatter: (value: string | null) => formatDate(value),
    },
    {
      field: 'renewal_end',
      headerName: t('amm.columns.renewalEnd'),
      width: 120,
      valueGetter: (_v, row) => row.last_renewal?.end_date ?? null,
      valueFormatter: (value: string | null) => formatDate(value),
    },
    {
      field: 'status',
      headerName: t('amm.columns.status'),
      width: 120,
      renderCell: (p) => <StatusChip value={p.row.status} />,
    },
    {
      field: 'urgency',
      headerName: t('amm.columns.urgency'),
      width: 140,
      renderCell: (p) => <UrgencyChip value={p.row.urgency} />,
    },
    {
      field: 'dossier_state',
      headerName: t('amm.columns.dossier'),
      width: 160,
      editable: true,
      type: 'singleSelect',
      valueOptions: DOSSIER_STATES.map((d) => ({ value: d, label: t(`dossier.${d}`) })),
      valueFormatter: (value: DossierState) => t(`dossier.${value}`),
    },
    {
      field: 'has_current_scan',
      headerName: t('amm.columns.scan'),
      width: 80,
      align: 'center',
      headerAlign: 'center',
      renderCell: (p) =>
        p.row.has_current_scan ? (
          <Tooltip title={t('amm.scanPresent')}>
            <PictureAsPdfIcon color="success" fontSize="small" data-testid="scan-present" />
          </Tooltip>
        ) : (
          <Tooltip title={t('amm.scanMissing')}>
            <ReportProblemIcon color="warning" fontSize="small" data-testid="scan-missing" />
          </Tooltip>
        ),
    },
    {
      field: 'actions',
      headerName: '',
      width: 60,
      sortable: false,
      renderCell: (p) => (
        <IconButton size="small" onClick={() => navigate(`/amms/${p.row.id}`)} aria-label={t('app.open')}>
          <OpenInNewIcon fontSize="small" />
        </IconButton>
      ),
    },
  ];

  const handleExport = async () => {
    setExporting(true);
    try {
      const blob = await exportAmms(filters);
      saveBlob(blob, `amm_export_${new Date().toISOString().slice(0, 10)}.xlsx`);
    } catch (err) {
      enqueueSnackbar(extractErrorMessage(err), { variant: 'error' });
    } finally {
      setExporting(false);
    }
  };

  const sortModel: GridSortModel = filters.ordering
    ? [{ field: filters.ordering.replace(/^-/, ''), sort: filters.ordering.startsWith('-') ? 'desc' : 'asc' }]
    : [];

  return (
    <Box>
      <PageHeader
        title={t('amm.title')}
        subtitle={query.data ? t('amm.rowsCount', { count: query.data.count }) : undefined}
        actions={
          <>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={handleExport}
              disabled={exporting}
            >
              {exporting ? t('amm.exporting') : t('amm.export')}
            </Button>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setCreateOpen(true)}
              data-testid="amm-create"
            >
              {t('amm.create')}
            </Button>
          </>
        }
      />
      <AmmFilters value={filters} onChange={setFilters} />
      <Paper variant="outlined" sx={{ height: 'calc(100vh - 300px)', minHeight: 420, width: '100%' }}>
        <DataGrid<Amm>
          rows={query.data?.results ?? []}
          columns={columns}
          rowCount={query.data?.count ?? 0}
          loading={query.isPending || query.isFetching}
          paginationMode="server"
          sortingMode="server"
          paginationModel={{ page: (filters.page ?? 1) - 1, pageSize }}
          onPaginationModelChange={(m) => {
            setPageSize(m.pageSize);
            setFilters({ ...filters, page: m.page + 1 });
          }}
          sortModel={sortModel}
          onSortModelChange={(m) =>
            setFilters({
              ...filters,
              ordering: m[0] ? `${m[0].sort === 'desc' ? '-' : ''}${m[0].field}` : undefined,
            })
          }
          pageSizeOptions={[25, 50, 100]}
          processRowUpdate={processRowUpdate}
          isCellEditable={(params) => canEditCountry(user, params.row.country_iso2)}
          disableRowSelectionOnClick
          density="compact"
          getRowClassName={(p) => `urgency-${p.row.urgency}`}
          sx={{ border: 0, '& .MuiDataGrid-cell:focus': { outline: 'none' } }}
          data-testid="amm-grid"
        />
      </Paper>
      <AmmCreateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(amm) => navigate(`/amms/${amm.id}`)}
      />
    </Box>
  );
}
