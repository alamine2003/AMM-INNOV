import { useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Link as MuiLink,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
} from '@mui/material';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useAlertActions } from '@/api/hooks/useAlerts';
import { useUsers } from '@/api/hooks/useUsers';
import type { Alert } from '@/api/types';
import { AlertStatusChip, SeverityChip } from '@/components/chips';
import { formatDate, formatDateTime } from '@/lib/dates';
import { extractErrorMessage } from '@/api/client';
import { canEditCountry, isHqOrAdmin, useAuthStore } from '@/features/auth/authStore';

export function AlertsTable({ alerts, hideAmm = false }: { alerts: Alert[]; hideAmm?: boolean }) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const user = useAuthStore((s) => s.user);
  const { acknowledge, assign, resolve } = useAlertActions();
  const users = useUsers(isHqOrAdmin(user));
  const [assigning, setAssigning] = useState<Alert | null>(null);
  const [assignee, setAssignee] = useState('');
  const [resolving, setResolving] = useState<Alert | null>(null);
  const [comment, setComment] = useState('');

  const onError = (e: unknown) => enqueueSnackbar(extractErrorMessage(e), { variant: 'error' });
  const assignableUsers = (users.data ?? []).filter((u) => u.is_active !== false);

  return (
    <>
      <TableContainer sx={{ overflowX: 'auto' }}>
        <Table size="small" data-testid="alerts-table">
          <TableHead>
            <TableRow>
              <TableCell>{t('alerts.columns.rule')}</TableCell>
              <TableCell>{t('alerts.columns.severity')}</TableCell>
              {!hideAmm && <TableCell>{t('alerts.columns.amm')}</TableCell>}
              <TableCell>{t('alerts.columns.dueDate')}</TableCell>
              <TableCell>{t('alerts.columns.status')}</TableCell>
              <TableCell>{t('alerts.columns.assignedTo')}</TableCell>
              <TableCell>{t('alerts.columns.triggeredAt')}</TableCell>
              <TableCell align="right">{t('app.actions')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {alerts.map((a) => {
              const editable = canEditCountry(user, a.country_iso2);
              return (
                <TableRow key={a.id} hover data-testid={`alert-${a.id}`}>
                  <TableCell>{a.rule_code}</TableCell>
                  <TableCell>
                    <SeverityChip value={a.severity} />
                  </TableCell>
                  {!hideAmm && (
                    <TableCell>
                      <MuiLink component={Link} to={`/amms/${a.amm_id}`} underline="hover">
                        {a.product_name}
                      </MuiLink>{' '}
                      ({a.country_iso2}) — {formatDate(a.effective_end_date)}
                    </TableCell>
                  )}
                  <TableCell>{formatDate(a.due_date)}</TableCell>
                  <TableCell>
                    <AlertStatusChip value={a.status} />
                  </TableCell>
                  <TableCell>{a.assigned_to_email ?? '—'}</TableCell>
                  <TableCell>{formatDateTime(a.triggered_at)}</TableCell>
                  <TableCell align="right">
                    {a.status !== 'RESOLVED' && editable && (
                      <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                        {a.status === 'OPEN' && (
                          <Button
                            size="small"
                            onClick={() =>
                              acknowledge.mutate(a.id, {
                                onSuccess: () =>
                                  enqueueSnackbar(t('alerts.acknowledged'), { variant: 'success' }),
                                onError,
                              })
                            }
                            data-testid={`ack-${a.id}`}
                          >
                            {t('alerts.acknowledge')}
                          </Button>
                        )}
                        {isHqOrAdmin(user) && (
                          <Button
                            size="small"
                            onClick={() => {
                              setAssigning(a);
                              setAssignee(a.assigned_to ?? '');
                            }}
                          >
                            {t('alerts.assign')}
                          </Button>
                        )}
                        <Button
                          size="small"
                          color="success"
                          onClick={() => {
                            setResolving(a);
                            setComment('');
                          }}
                        >
                          {t('alerts.resolve')}
                        </Button>
                      </Stack>
                    )}
                    {a.status === 'RESOLVED' && (a.comment || a.resolution)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={!!assigning} onClose={() => setAssigning(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('alerts.assignTo')}</DialogTitle>
        <DialogContent>
          <TextField
            select
            fullWidth
            sx={{ mt: 1 }}
            label={t('app.user')}
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
          >
            {assignableUsers.map((u) => (
              <MenuItem key={u.id} value={u.id}>
                {u.first_name} {u.last_name} — {u.email}
              </MenuItem>
            ))}
          </TextField>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAssigning(null)}>{t('app.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!assignee || assign.isPending}
            onClick={() =>
              assigning &&
              assign.mutate(
                { id: assigning.id, user_id: assignee },
                {
                  onSuccess: () => {
                    enqueueSnackbar(t('alerts.assigned'), { variant: 'success' });
                    setAssigning(null);
                  },
                  onError,
                },
              )
            }
          >
            {t('app.confirm')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!resolving} onClose={() => setResolving(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t('alerts.resolveTitle')}</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            multiline
            minRows={3}
            sx={{ mt: 1 }}
            label={t('alerts.comment')}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            required
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResolving(null)}>{t('app.cancel')}</Button>
          <Button
            variant="contained"
            color="success"
            disabled={!comment.trim() || resolve.isPending}
            onClick={() =>
              resolving &&
              resolve.mutate(
                { id: resolving.id, comment },
                {
                  onSuccess: () => {
                    enqueueSnackbar(t('alerts.resolved'), { variant: 'success' });
                    setResolving(null);
                  },
                  onError,
                },
              )
            }
          >
            {t('app.confirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
