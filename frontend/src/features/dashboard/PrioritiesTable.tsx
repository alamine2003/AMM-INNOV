import {
  Link as MuiLink,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import type { Amm } from '@/api/types';
import { StatusChip, UrgencyChip } from '@/components/chips';
import { formatDate, formatRemaining } from '@/lib/dates';

export function PrioritiesTable({ amms, showCountry = false }: { amms: Amm[]; showCountry?: boolean }) {
  const { t } = useTranslation();
  return (
    <TableContainer sx={{ overflowX: 'auto' }}>
      <Table size="small" data-testid="priorities-table">
        <TableHead>
          <TableRow>
            {showCountry && <TableCell>{t('amm.columns.country')}</TableCell>}
            <TableCell>{t('amm.columns.product')}</TableCell>
            <TableCell>{t('amm.columns.status')}</TableCell>
            <TableCell>{t('amm.columns.urgency')}</TableCell>
            <TableCell>{t('amm.columns.effectiveEnd')}</TableCell>
            <TableCell>{t('amm.columns.remaining')}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {amms.map((a) => (
            <TableRow key={a.id} hover>
              {showCountry && <TableCell>{a.country_iso2}</TableCell>}
              <TableCell>
                <MuiLink component={Link} to={`/amms/${a.id}`} underline="hover">
                  {a.product_name}
                </MuiLink>
              </TableCell>
              <TableCell>
                <StatusChip value={a.status} />
              </TableCell>
              <TableCell>
                <UrgencyChip value={a.urgency} />
              </TableCell>
              <TableCell>{formatDate(a.effective_end_date)}</TableCell>
              <TableCell>{formatRemaining(a.effective_end_date)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
