import { Fragment, useMemo, useState, type InputHTMLAttributes } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { usePermissions, useSavePermissions } from '@/api/hooks/usePermissions';
import type { PermissionGrant, PermissionMatrix } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';

type Draft = Record<string, boolean>;
const cell = (action: string, role: string) => `${action}|${role}`;

function groups(matrix: PermissionMatrix) {
  const result: { name: string; actions: PermissionMatrix['actions'] }[] = [];
  for (const action of matrix.actions) {
    const last = result[result.length - 1];
    if (last && last.name === action.group) last.actions.push(action);
    else result.push({ name: action.group, actions: [action] });
  }
  return result;
}

/**
 * Permissions (CEO) : qui peut faire quoi, rôle par rôle. Le CEO garde toujours tous les droits
 * et le droit de régler les permissions ne se règle pas : personne ne peut s'enfermer dehors.
 * Chaque changement est gardé dans l'audit. Le périmètre pays (ce qu'un utilisateur pays voit)
 * ne se règle pas ici.
 */
export default function PermissionsPage() {
  const permissions = usePermissions();
  const save = useSavePermissions();
  const { enqueueSnackbar } = useSnackbar();
  const [draft, setDraft] = useState<Draft>({});
  const matrix = permissions.data;
  const sections = useMemo(() => (matrix ? groups(matrix) : []), [matrix]);

  const value = (action: string, role: string, stored: boolean) => draft[cell(action, role)] ?? stored;
  const changes: PermissionGrant[] = matrix
    ? matrix.actions.flatMap((item) =>
        matrix.roles
          .filter((role) => role.editable && !item.locked)
          .map((role) => ({
            action: item.action,
            role: role.value,
            allowed: value(item.action, role.value, item.roles[role.value]),
          }))
          .filter((grant) => grant.allowed !== item.roles[grant.role]),
      )
    : [];

  const restoreDefaults = () => {
    if (!matrix) return;
    const next: Draft = {};
    for (const item of matrix.actions) {
      for (const role of matrix.roles) {
        if (role.editable && !item.locked)
          next[cell(item.action, role.value)] = item.defaults.includes(role.value);
      }
    }
    setDraft(next);
  };

  const submit = () =>
    save.mutate(changes, {
      onSuccess: () => {
        setDraft({});
        enqueueSnackbar('Permissions enregistrées. Elles s’appliquent dès la prochaine action de chacun.', {
          variant: 'success',
        });
      },
      onError: (error) => enqueueSnackbar(extractErrorMessage(error), { variant: 'error' }),
    });

  return (
    <>
      <PageHeader
        title="Permissions"
        subtitle="Cochez ce que chaque rôle peut faire. Le CEO garde toujours tous les droits ; chaque changement est tracé dans l’audit."
        actions={
          <Stack direction="row" gap={1}>
            <Button size="small" onClick={restoreDefaults} disabled={!matrix || save.isPending}>
              Réglages par défaut
            </Button>
            <Button
              size="small"
              onClick={() => setDraft({})}
              disabled={changes.length === 0 || save.isPending}
            >
              Annuler
            </Button>
            <Button
              variant="contained"
              size="small"
              onClick={submit}
              disabled={changes.length === 0 || save.isPending}
              data-testid="save-permissions"
            >
              Enregistrer{changes.length > 0 ? ` (${changes.length})` : ''}
            </Button>
          </Stack>
        }
      />
      {permissions.isError && <Alert severity="error">{extractErrorMessage(permissions.error)}</Alert>}
      {matrix && (
        <Paper variant="outlined">
          <Table size="small" data-testid="permissions-table">
            <TableHead>
              <TableRow>
                <TableCell>Action</TableCell>
                {matrix.roles.map((role) => (
                  <TableCell key={role.value} align="center" sx={{ whiteSpace: 'nowrap' }}>
                    {role.label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {sections.map((section) => (
                <Fragment key={section.name}>
                  <TableRow>
                    <TableCell colSpan={matrix.roles.length + 1} sx={{ bgcolor: 'action.hover', py: 0.5 }}>
                      <Typography variant="overline">{section.name}</Typography>
                    </TableCell>
                  </TableRow>
                  {section.actions.map((item) => (
                    <TableRow key={item.action} hover>
                      <TableCell>
                        {item.label}
                        {item.locked && (
                          <Typography component="span" variant="caption" color="text.secondary">
                            {' '}
                            · réservé au CEO
                          </Typography>
                        )}
                      </TableCell>
                      {matrix.roles.map((role) => {
                        const stored = item.roles[role.value];
                        const checked = value(item.action, role.value, stored);
                        const fixed = !role.editable || item.locked;
                        const box = (
                          <Checkbox
                            size="small"
                            checked={checked}
                            disabled={fixed || save.isPending}
                            onChange={(event) =>
                              setDraft((current) => ({
                                ...current,
                                [cell(item.action, role.value)]: event.target.checked,
                              }))
                            }
                            inputProps={
                              {
                                'aria-label': `${item.label} — ${role.label}`,
                                'data-testid': `perm-${item.action}-${role.value}`,
                              } as InputHTMLAttributes<HTMLInputElement>
                            }
                            sx={checked !== stored ? { color: 'warning.main' } : undefined}
                          />
                        );
                        return (
                          <TableCell key={role.value} align="center">
                            {fixed ? (
                              <Tooltip
                                title={role.editable ? 'Ne se règle pas' : 'Le CEO garde tous les droits'}
                              >
                                <span>{box}</span>
                              </Tooltip>
                            ) : (
                              box
                            )}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  ))}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}
    </>
  );
}
