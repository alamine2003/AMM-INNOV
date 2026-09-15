import { Box, Chip, Tooltip } from '@mui/material';
import CloudDoneIcon from '@mui/icons-material/CloudDone';
import CloudOffIcon from '@mui/icons-material/CloudOff';
import CloudQueueIcon from '@mui/icons-material/CloudQueue';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import { useTranslation } from 'react-i18next';
import type { Health } from '@/api/types';
import { toApiHealthState, useHealth, type ApiHealthState } from '@/api/hooks/useHealth';

export interface ApiHealthBadgeViewProps {
  state: ApiHealthState;
  /** Dernière réponse conforme ; absente en `checking`, ignorée en `unreachable`. */
  health?: Health;
}

// Contrastes (texte 13 px gras du Chip = texte normal au sens WCAG), valeurs du thème
// (src/app/theme.ts) : blanc sur primary.main ≈ 7,2:1 (checking, online, unreachable) ; blanc
// sur error.main ≈ 5,6:1 (degraded) ; bordure blanche ≈ 7,2:1 contre la barre et 5,6:1 contre le
// rouge (contraste non textuel ≥ 3:1). La couleur ne porte jamais seule l'information : le
// libellé change toujours avec l'état.
const NEUTRAL_SX = {
  color: 'inherit',
  borderColor: 'rgba(255,255,255,0.4)',
  '& .MuiChip-icon': { color: 'inherit' },
} as const;

const DEGRADED_SX = { border: 1, borderColor: 'common.white' } as const;

export function ApiHealthBadgeView({ state, health }: ApiHealthBadgeViewProps) {
  const { t } = useTranslation();

  const version = health?.version ? health.version : t('health.versionUnknown');

  const longLabel =
    state === 'checking'
      ? t('health.checking')
      : state === 'online'
        ? t('health.online', { version })
        : state === 'degraded'
          ? t('health.degraded', { version })
          : t('health.unreachable');

  const shortLabel = t(`health.short.${state}`);

  const icon =
    state === 'checking' ? (
      <CloudQueueIcon fontSize="small" />
    ) : state === 'online' ? (
      <CloudDoneIcon fontSize="small" />
    ) : state === 'degraded' ? (
      <ReportProblemIcon fontSize="small" />
    ) : (
      <CloudOffIcon fontSize="small" />
    );

  const detailLine = (state: 'database' | 'redis', up: boolean) =>
    t(`health.tooltip.${state}`, { state: t(up ? 'health.tooltip.up' : 'health.tooltip.down') });

  const tooltip =
    state === 'checking' ? (
      t('health.checking')
    ) : state === 'unreachable' ? (
      t('health.tooltip.unreachable')
    ) : (
      <Box component="span" sx={{ display: 'block' }}>
        <Box component="span" sx={{ display: 'block' }}>
          {t('health.tooltip.version', { version })}
        </Box>
        <Box component="span" sx={{ display: 'block' }}>
          {detailLine('database', !!health?.database)}
        </Box>
        <Box component="span" sx={{ display: 'block' }}>
          {detailLine('redis', !!health?.redis)}
        </Box>
      </Box>
    );

  return (
    <Tooltip title={tooltip}>
      <Chip
        size="small"
        variant={state === 'degraded' ? 'filled' : 'outlined'}
        color={state === 'degraded' ? 'error' : undefined}
        icon={icon}
        label={
          <>
            <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
              {longLabel}
            </Box>
            <Box component="span" sx={{ display: { xs: 'inline', sm: 'none' } }}>
              {shortLabel}
            </Box>
          </>
        }
        data-testid="api-health-badge"
        data-status={state}
        aria-live="polite"
        sx={{
          ...(state === 'degraded' ? DEGRADED_SX : NEUTRAL_SX),
          maxWidth: { sm: 320 },
        }}
      />
    </Tooltip>
  );
}

export function ApiHealthBadge() {
  const query = useHealth();
  const state = toApiHealthState({ status: query.status, data: query.data });
  return <ApiHealthBadgeView state={state} health={query.data} />;
}
