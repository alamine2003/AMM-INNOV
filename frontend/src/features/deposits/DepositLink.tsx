import { Button, Tooltip } from '@mui/material';
import AssignmentTurnedInIcon from '@mui/icons-material/AssignmentTurnedIn';
import { Link, useNavigate } from 'react-router';
import { useOpenDeposit } from '@/api/hooks/useDeposits';
import { useRenewals } from '@/api/hooks/useRenewals';
import type { AmmStatus } from '@/api/types';
import { useAuthStore } from '@/features/auth/authStore';
import { useFail } from './sections';

const OPEN = ['PLANIFIE', 'EN_PREPARATION', 'DEPOSE', 'EN_INSTRUCTION'];

/**
 * Depuis la fiche AMM : le dossier de dépôt du renouvellement en cours, ou (siège) le bouton
 * pour le monter quand l'AMM est à renouveler.
 */
export function DepositLink({ ammId, status }: { ammId: string; status: AmmStatus }) {
  const renewals = useRenewals(ammId);
  const open = useOpenDeposit();
  const navigate = useNavigate();
  const fail = useFail();
  const user = useAuthStore((s) => s.user);
  const hq = user?.role === 'CEO_ADMIN' || user?.role === 'HQ_REGULATORY';
  if (!renewals.data) return null;
  const followed =
    renewals.data.find((r) => r.deposit_id && OPEN.includes(r.workflow_status)) ??
    renewals.data.find((r) => r.deposit_id);
  if (followed?.deposit_id) {
    return (
      <Button
        component={Link}
        to={`/depots/${followed.deposit_id}`}
        variant="outlined"
        size="small"
        startIcon={<AssignmentTurnedInIcon />}
      >
        Dossier de dépôt · renouvellement n°{followed.sequence}
      </Button>
    );
  }
  const pending = renewals.data.some(
    (r) => r.workflow_status === 'DEPOSE' || r.workflow_status === 'EN_INSTRUCTION',
  );
  if (!hq || pending || (status !== 'A_RENOUVELER' && status !== 'EXPIRE')) return null;
  return (
    <Tooltip title="Ouvrir le dossier de dépôt du prochain renouvellement (rubrique Dépôts AMM)">
      <Button
        variant="contained"
        size="small"
        startIcon={<AssignmentTurnedInIcon />}
        disabled={open.isPending}
        onClick={() => open.mutate(ammId, { onSuccess: (d) => navigate(`/depots/${d.id}`), onError: fail })}
      >
        Monter le dossier de dépôt
      </Button>
    </Tooltip>
  );
}
