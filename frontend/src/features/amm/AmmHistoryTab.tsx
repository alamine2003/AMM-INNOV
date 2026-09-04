import {
  Box,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useAmmHistory } from '@/api/hooks/useAmms';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { formatDateTime } from '@/lib/dates';

const show = (v: unknown) =>
  v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v);

export function AmmHistoryTab({ ammId }: { ammId: string }) {
  const { t } = useTranslation();
  const history = useAmmHistory(ammId);
  if (history.isPending) return <LoadingBlock />;
  if (history.isError) return <ErrorBlock error={history.error} onRetry={() => history.refetch()} />;
  if (history.data.length === 0) return <EmptyBlock text={t('amm.history.empty')} />;
  return (
    <Box>
      {history.data.map((entry, i) => (
        <Box key={`${entry.date}-${i}`} sx={{ mb: 3 }}>
          <Typography
            variant="subtitle2"
            sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}
          >
            {formatDateTime(entry.date)} — {entry.user_email}
            <Chip size="small" label={entry.type} variant="outlined" />
          </Typography>
          <TableContainer sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('amm.history.field')}</TableCell>
                  <TableCell>{t('amm.history.old')}</TableCell>
                  <TableCell>{t('amm.history.new')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {entry.changes.map((c, j) => (
                  <TableRow key={j}>
                    <TableCell>{c.field}</TableCell>
                    <TableCell sx={{ color: 'text.secondary' }}>{show(c.old)}</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>{show(c.new)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      ))}
    </Box>
  );
}
