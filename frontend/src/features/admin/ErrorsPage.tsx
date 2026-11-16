import { Fragment, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Collapse,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { useErrors, useResolveError, type ErrorState } from '@/api/hooks/useErrors';
import type { ErrorEvent } from '@/api/types';
import { useTranslation } from 'react-i18next';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/dates';

const STATES: ErrorState[] = ['open', 'resolved', 'all'];

const SOURCE_COLORS: Record<ErrorEvent['source'], 'error' | 'warning' | 'info'> = {
  server: 'error',
  worker: 'warning',
  interface: 'info',
};

/**
 * Journal des erreurs (CEO) : ce qui a planté en production, côté serveur, tâches de fond ou
 * interface. La même erreur se compte au lieu de se répéter ; résolue, elle se rouvre si elle
 * revient. Rien ne sort d'AMM GH (pas de service externe).
 */
export default function ErrorsPage() {
  const { t } = useTranslation();
  const [state, setState] = useState<ErrorState>('open');
  const [page, setPage] = useState(1);
  const [opened, setOpened] = useState<string | null>(null);
  const errors = useErrors(state, page);
  const resolve = useResolveError();
  const { enqueueSnackbar } = useSnackbar();
  const rows = errors.data?.results ?? [];

  return (
    <>
      <PageHeader title={t('adminPages.errors.title')} subtitle={t('adminPages.errors.subtitle')} />
      <Stack direction="row" alignItems="center" gap={2} sx={{ mb: 2 }}>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={state}
          onChange={(_, value: ErrorState | null) => {
            if (value) {
              setState(value);
              setPage(1);
            }
          }}
        >
          {STATES.map((option) => (
            <ToggleButton key={option} value={option}>
              {t(`adminPages.errors.states.${option}`)}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        {errors.data && (
          <Typography variant="body2" color="text.secondary">
            {t('adminPages.errors.count', { count: errors.data.count })}
          </Typography>
        )}
      </Stack>
      {errors.isError && <Alert severity="error">{extractErrorMessage(errors.error)}</Alert>}
      <Paper variant="outlined">
        <Table size="small" data-testid="errors-table">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox" />
              <TableCell>{t('adminPages.errors.columns.lastSeen')}</TableCell>
              <TableCell>{t('adminPages.errors.columns.source')}</TableCell>
              <TableCell>{t('adminPages.errors.columns.error')}</TableCell>
              <TableCell>{t('adminPages.errors.columns.where')}</TableCell>
              <TableCell align="right">{t('adminPages.errors.columns.times')}</TableCell>
              <TableCell align="right">{t('adminPages.errors.columns.state')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 && !errors.isLoading && (
              <TableRow>
                <TableCell colSpan={7}>
                  <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                    {state === 'open' ? t('adminPages.errors.emptyOpen') : t('adminPages.errors.empty')}
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {rows.map((event) => (
              <Fragment key={event.id}>
                <TableRow hover sx={{ '& > td': { borderBottom: opened === event.id ? 0 : undefined } }}>
                  <TableCell padding="checkbox">
                    <IconButton
                      size="small"
                      aria-label={
                        opened === event.id
                          ? t('adminPages.errors.hideDetail')
                          : t('adminPages.errors.showDetail')
                      }
                      onClick={() => setOpened(opened === event.id ? null : event.id)}
                    >
                      {opened === event.id ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                    </IconButton>
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(event.last_seen)}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      variant="outlined"
                      color={SOURCE_COLORS[event.source]}
                      label={event.source_label}
                    />
                  </TableCell>
                  <TableCell sx={{ maxWidth: 420 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {event.kind}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ wordBreak: 'break-word' }}>
                      {event.message}
                    </Typography>
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                    {event.location || '—'}
                  </TableCell>
                  <TableCell align="right">{event.count}</TableCell>
                  <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                    {event.resolved_at ? (
                      <Chip
                        size="small"
                        color="success"
                        variant="outlined"
                        label={t('adminPages.errors.resolvedOn', { date: formatDateTime(event.resolved_at) })}
                      />
                    ) : (
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={resolve.isPending}
                        onClick={() =>
                          resolve.mutate(event.id, {
                            onSuccess: () =>
                              enqueueSnackbar(t('adminPages.errors.resolvedToast'), { variant: 'success' }),
                            onError: (error) =>
                              enqueueSnackbar(extractErrorMessage(error), { variant: 'error' }),
                          })
                        }
                      >
                        {t('adminPages.errors.resolve')}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell colSpan={7} sx={{ py: 0 }}>
                    <Collapse in={opened === event.id} unmountOnExit>
                      <Box sx={{ py: 1.5 }}>
                        <Typography variant="caption" color="text.secondary" component="p" sx={{ mb: 1 }}>
                          {t('adminPages.errors.firstSeen', {
                            date: formatDateTime(event.first_seen),
                            version: event.version || '—',
                          })}
                          {event.last_user
                            ? ` · ${t('adminPages.errors.lastUser', { user: event.last_user })}`
                            : ''}
                        </Typography>
                        <Box
                          component="pre"
                          sx={{
                            m: 0,
                            p: 1.5,
                            maxHeight: 320,
                            overflow: 'auto',
                            bgcolor: 'action.hover',
                            borderRadius: 1,
                            fontSize: 12,
                            whiteSpace: 'pre-wrap',
                          }}
                        >
                          {event.detail || t('adminPages.errors.noDetail')}
                        </Box>
                      </Box>
                    </Collapse>
                  </TableCell>
                </TableRow>
              </Fragment>
            ))}
          </TableBody>
        </Table>
      </Paper>
      {errors.data && (errors.data.next || page > 1) && (
        <Stack direction="row" justifyContent="flex-end" gap={1} sx={{ mt: 1 }}>
          <Button size="small" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            {t('common.pagination.previous')}
          </Button>
          <Button size="small" disabled={!errors.data.next} onClick={() => setPage(page + 1)}>
            {t('common.pagination.next')}
          </Button>
        </Stack>
      )}
    </>
  );
}
