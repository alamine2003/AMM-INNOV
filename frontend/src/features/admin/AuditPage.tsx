import { useState } from 'react';
import {
  Alert,
  Button,
  Chip,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { extractErrorMessage } from '@/api/client';
import { useAudit, useAuditFilters, type AuditQuery } from '@/api/hooks/useAudit';
import { useCountries } from '@/api/hooks/useCatalog';
import type { AuditAction, AuditEvent } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { formatDate, formatDateTime } from '@/lib/dates';

const ACTION_COLORS: Record<AuditAction, 'default' | 'primary' | 'success' | 'warning' | 'info'> = {
  created: 'success',
  updated: 'primary',
  login: 'default',
  deleted: 'warning',
  restored: 'info',
};

/** Une date ISO (2026-01-01) s'affiche comme partout ailleurs (01/01/2026). */
const shown = (value: string | null) =>
  value === null ? '—' : /^\d{4}-\d{2}-\d{2}$/.test(value) ? formatDate(value) : value;

function Detail({ event }: { event: AuditEvent }) {
  if (event.changes.length > 0) {
    return (
      <Stack gap={0.25}>
        {event.changes.map((change, index) => (
          <Typography key={`${change.field}-${index}`} variant="caption" sx={{ display: 'block' }}>
            <strong>{change.field}</strong>
            {change.old !== null || change.new !== null ? (
              <>
                {' '}
                : {shown(change.old)} → {shown(change.new)}
              </>
            ) : (
              ' modifié'
            )}
          </Typography>
        ))}
      </Stack>
    );
  }
  const parts = [
    event.reason,
    event.action === 'deleted' && event.rows > 1
      ? `avec ${event.rows - 1} élément${event.rows > 2 ? 's' : ''} lié${event.rows > 2 ? 's' : ''}`
      : '',
  ].filter(Boolean);
  return (
    <Typography variant="caption" color="text.secondary">
      {parts.join(' · ') || '—'}
    </Typography>
  );
}

/**
 * Audit et traçabilité (CEO et siège) : qui a fait quoi, quand, dans toute l'application.
 * Créations, modifications (champ par champ), connexions, mises à la corbeille et restaurations.
 * Rien n'est saisi pour l'audit : il relit l'historique et la corbeille.
 */
export default function AuditPage() {
  const [query, setQuery] = useState<AuditQuery>({});
  const [page, setPage] = useState(1);
  const audit = useAudit(query, page);
  const filters = useAuditFilters();
  const countries = useCountries();
  const rows = audit.data?.results ?? [];

  const update = (patch: Partial<AuditQuery>) => {
    setQuery((current) => ({ ...current, ...patch }));
    setPage(1);
  };
  const select = (label: string, name: keyof AuditQuery, options: { value: string; label: string }[]) => (
    <TextField
      select
      size="small"
      label={label}
      value={query[name] ?? ''}
      onChange={(event) => update({ [name]: event.target.value })}
      sx={{ minWidth: 170 }}
      inputProps={{ 'data-testid': `audit-filter-${name}` }}
    >
      <MenuItem value="">Tous</MenuItem>
      {options.map((option) => (
        <MenuItem key={option.value} value={option.value}>
          {option.label}
        </MenuItem>
      ))}
    </TextField>
  );

  return (
    <>
      <PageHeader
        title="Audit et traçabilité"
        subtitle="Qui a fait quoi, quand : créations, modifications, connexions, suppressions et restaurations."
      />
      <Stack direction="row" flexWrap="wrap" alignItems="center" gap={1.5} sx={{ mb: 2 }}>
        {select(
          'Personne',
          'user',
          (filters.data?.people ?? []).map((person) => ({
            value: person.id,
            label: person.active ? person.name : `${person.name} (désactivé)`,
          })),
        )}
        {select('Action', 'action', filters.data?.actions ?? [])}
        {select('Type', 'model', filters.data?.types ?? [])}
        {select(
          'Pays',
          'country',
          (countries.data ?? []).map((country) => ({ value: country.iso2, label: country.name })),
        )}
        <TextField
          size="small"
          type="date"
          label="Du"
          value={query.since ?? ''}
          onChange={(event) => update({ since: event.target.value })}
          InputLabelProps={{ shrink: true }}
        />
        <TextField
          size="small"
          type="date"
          label="Au"
          value={query.until ?? ''}
          onChange={(event) => update({ until: event.target.value })}
          InputLabelProps={{ shrink: true }}
        />
        {Object.values(query).some(Boolean) && (
          <Button
            size="small"
            onClick={() => update({ user: '', model: '', action: '', country: '', since: '', until: '' })}
          >
            Effacer les filtres
          </Button>
        )}
        {audit.data && (
          <Typography variant="body2" color="text.secondary" sx={{ ml: 'auto' }}>
            {audit.data.count} événement{audit.data.count > 1 ? 's' : ''}
          </Typography>
        )}
      </Stack>
      {audit.isError && <Alert severity="error">{extractErrorMessage(audit.error)}</Alert>}
      <Paper variant="outlined">
        <Table size="small" data-testid="audit-table">
          <TableHead>
            <TableRow>
              <TableCell>Date</TableCell>
              <TableCell>Par</TableCell>
              <TableCell>Action</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Élément</TableCell>
              <TableCell>Pays</TableCell>
              <TableCell>Détail</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 && !audit.isLoading && (
              <TableRow>
                <TableCell colSpan={7}>
                  <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                    Aucun événement pour ces filtres.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {rows.map((event) => (
              <TableRow key={event.id} hover sx={{ verticalAlign: 'top' }}>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(event.at)}</TableCell>
                <TableCell>{event.user ?? 'Système'}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    variant="outlined"
                    color={ACTION_COLORS[event.action]}
                    label={event.action_label}
                  />
                </TableCell>
                <TableCell>{event.type}</TableCell>
                <TableCell sx={{ maxWidth: 320 }}>{event.label}</TableCell>
                <TableCell>{event.country || '—'}</TableCell>
                <TableCell sx={{ maxWidth: 360 }}>
                  <Detail event={event} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      {audit.data && audit.data.pages > 1 && (
        <Stack direction="row" justifyContent="flex-end" alignItems="center" gap={1} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Page {audit.data.page} / {audit.data.pages}
          </Typography>
          <Button size="small" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Précédent
          </Button>
          <Button size="small" disabled={page >= audit.data.pages} onClick={() => setPage(page + 1)}>
            Suivant
          </Button>
        </Stack>
      )}
    </>
  );
}
