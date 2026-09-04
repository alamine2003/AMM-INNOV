import { useState } from 'react';
import {
  Badge,
  Box,
  Button,
  Divider,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Popover,
  Typography,
} from '@mui/material';
import NotificationsIcon from '@mui/icons-material/Notifications';
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useNotificationActions, useNotifications, useUnreadCount } from '@/api/hooks/useNotifications';
import { useAuthStore } from '@/features/auth/authStore';
import { useRealtimeStore } from '@/realtime/realtimeStore';
import { formatDateTime } from '@/lib/dates';

export function NotificationBell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const access = useAuthStore((s) => s.access);
  const status = useRealtimeStore((s) => s.status);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const open = !!anchor;
  const unread = useUnreadCount(!!access, status === 'connected' ? false : 60_000);
  const list = useNotifications(false, open);
  const { markRead, markAllRead } = useNotificationActions();

  return (
    <>
      <IconButton
        color="inherit"
        onClick={(e) => setAnchor(e.currentTarget)}
        aria-label={t('notifications.title')}
        data-testid="notification-bell"
      >
        <Badge badgeContent={unread.data ?? 0} color="error" data-testid="notification-badge">
          <NotificationsIcon />
        </Badge>
      </IconButton>
      <Popover
        open={open}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { width: 380, maxHeight: 480 } } }}
      >
        <Box sx={{ px: 2, py: 1, display: 'flex', alignItems: 'center' }}>
          <Typography variant="subtitle1" sx={{ flexGrow: 1 }}>
            {t('notifications.title')}
          </Typography>
          <Button size="small" onClick={() => markAllRead.mutate()} disabled={!unread.data}>
            {t('notifications.markAllRead')}
          </Button>
        </Box>
        <Divider />
        <List dense disablePadding>
          {(list.data ?? []).length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
              {t('notifications.empty')}
            </Typography>
          )}
          {(list.data ?? []).map((n) => (
            <ListItemButton
              key={n.id}
              onClick={() => {
                if (!n.read_at) markRead.mutate(n.id);
                setAnchor(null);
                if (n.link) navigate(n.link);
              }}
              sx={{ bgcolor: n.read_at ? undefined : 'action.selected', alignItems: 'flex-start' }}
            >
              <ListItemText
                primary={n.title}
                secondary={
                  <>
                    {n.body}
                    <Typography component="span" variant="caption" display="block" color="text.secondary">
                      {formatDateTime(n.sent_at)}
                    </Typography>
                  </>
                }
                primaryTypographyProps={{ fontWeight: n.read_at ? 400 : 600 }}
              />
            </ListItemButton>
          ))}
        </List>
      </Popover>
    </>
  );
}
