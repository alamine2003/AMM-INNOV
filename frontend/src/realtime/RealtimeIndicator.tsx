import { Chip, Tooltip } from '@mui/material';
import WifiIcon from '@mui/icons-material/Wifi';
import SyncIcon from '@mui/icons-material/Sync';
import WifiOffIcon from '@mui/icons-material/WifiOff';
import { useTranslation } from 'react-i18next';
import { useRealtimeStore } from './realtimeStore';

export function RealtimeIndicator() {
  const status = useRealtimeStore((s) => s.status);
  const { t } = useTranslation();
  const config = {
    connected: {
      icon: <WifiIcon fontSize="small" />,
      color: 'success' as const,
      label: t('realtime.connected'),
    },
    reconnecting: {
      icon: <SyncIcon fontSize="small" />,
      color: 'warning' as const,
      label: t('realtime.reconnecting'),
    },
    polling: {
      icon: <WifiOffIcon fontSize="small" />,
      color: 'default' as const,
      label: t('realtime.polling'),
    },
    idle: { icon: <WifiOffIcon fontSize="small" />, color: 'default' as const, label: t('realtime.idle') },
  }[status];
  return (
    <Tooltip title={config.label}>
      <Chip
        size="small"
        icon={config.icon}
        color={config.color}
        variant="outlined"
        label={status === 'connected' ? 'Live' : status === 'reconnecting' ? '…' : 'Polling'}
        data-testid="realtime-indicator"
        data-status={status}
        sx={{
          color: 'inherit',
          borderColor: 'rgba(255,255,255,0.4)',
          '& .MuiChip-icon': { color: 'inherit' },
        }}
      />
    </Tooltip>
  );
}
