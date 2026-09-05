import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  FormControlLabel,
  LinearProgress,
  Link as MuiLink,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { Link, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useImports, useStartImport } from '@/api/hooks/useImports';
import { PageHeader } from '@/components/PageHeader';
import { FileDropzone } from '@/components/FileDropzone';
import { EmptyBlock } from '@/components/QueryState';
import { formatDateTime } from '@/lib/dates';
import { extractErrorMessage } from '@/api/client';

export const statusColor = (s: string): 'success' | 'error' | 'warning' | 'default' =>
  s === 'DONE'
    ? 'success'
    : s === 'FAILED'
      ? 'error'
      : s === 'RUNNING' || s === 'PENDING'
        ? 'warning'
        : 'default';

export default function ImportsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const imports = useImports();
  const start = useStartImport();
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [dryRun, setDryRun] = useState(false);

  const launch = () => {
    if (!file) return;
    start.mutate(
      { file, dryRun, onProgress: setProgress },
      {
        onSuccess: (batch) => {
          enqueueSnackbar(t('admin.imports.started'), { variant: 'success' });
          setFile(null);
          navigate(`/admin/imports/${batch.id}`);
        },
        onError: (e) => enqueueSnackbar(extractErrorMessage(e), { variant: 'error' }),
      },
    );
  };

  return (
    <Box>
      <PageHeader title={t('admin.imports.title')} />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack spacing={2}>
            <FileDropzone
              onFile={setFile}
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              label={t('admin.imports.dropzone')}
              file={file}
              disabled={start.isPending}
            />
            <FormControlLabel
              control={<Checkbox checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />}
              label={t('admin.imports.dryRun')}
            />
            {start.isPending && progress !== null && (
              <LinearProgress variant="determinate" value={progress} />
            )}
            {start.isError && <Alert severity="error">{extractErrorMessage(start.error)}</Alert>}
            <Box>
              <Button variant="contained" disabled={!file || start.isPending} onClick={launch}>
                {t('admin.imports.upload')}
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>
      <Typography variant="h6" gutterBottom>
        {t('admin.imports.history')}
      </Typography>
      <Paper variant="outlined">
        {(imports.data ?? []).length === 0 ? (
          <EmptyBlock />
        ) : (
          <TableContainer sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('app.date')}</TableCell>
                  <TableCell>Fichier</TableCell>
                  <TableCell>{t('admin.imports.status')}</TableCell>
                  <TableCell>{t('admin.imports.created')}</TableCell>
                  <TableCell>{t('admin.imports.updated')}</TableCell>
                  <TableCell>{t('admin.imports.errorCount')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(imports.data ?? []).map((b) => {
                  const s = ((b.summary as Record<string, unknown> | null)?.totals ?? {}) as Record<
                    string,
                    number
                  >;
                  return (
                    <TableRow key={b.id} hover>
                      <TableCell>{formatDateTime(b.created_at)}</TableCell>
                      <TableCell>
                        <MuiLink component={Link} to={`/admin/imports/${b.id}`} underline="hover">
                          {b.filename || b.id}
                        </MuiLink>
                      </TableCell>
                      <TableCell>
                        <Chip size="small" label={b.status} color={statusColor(b.status)} />
                        {b.dry_run && (
                          <Chip size="small" label={t('admin.imports.dryRunChip')} sx={{ ml: 0.5 }} />
                        )}
                      </TableCell>
                      <TableCell>{s.created ?? '—'}</TableCell>
                      <TableCell>{s.updated ?? '—'}</TableCell>
                      <TableCell>{s.errors ?? '—'}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
    </Box>
  );
}
