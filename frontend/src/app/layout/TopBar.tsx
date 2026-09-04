import { useState } from 'react';
import {
  AppBar,
  Avatar,
  Box,
  Chip,
  Divider,
  IconButton,
  ListItemIcon,
  Menu,
  MenuItem,
  Toolbar,
  Typography,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import LogoutIcon from '@mui/icons-material/Logout';
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/features/auth/authStore';
import { useLogout } from '@/api/hooks/useAuth';
import { RealtimeIndicator } from '@/realtime/RealtimeIndicator';
import { NotificationBell } from '@/features/notifications/NotificationBell';
import { DRAWER_WIDTH } from './SideNav';

export function TopBar({ onMenuClick }: { onMenuClick: () => void }) {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const logout = useLogout();
  const navigate = useNavigate();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  const initials = user
    ? `${user.first_name?.[0] ?? ''}${user.last_name?.[0] ?? ''}`.toUpperCase() || user.email[0].toUpperCase()
    : '?';

  return (
    <AppBar
      position="fixed"
      sx={{ width: { md: `calc(100% - ${DRAWER_WIDTH}px)` }, ml: { md: `${DRAWER_WIDTH}px` } }}
    >
      <Toolbar sx={{ gap: 1 }}>
        <IconButton
          color="inherit"
          edge="start"
          onClick={onMenuClick}
          sx={{ display: { md: 'none' } }}
          aria-label={t('nav.openMenu')}
        >
          <MenuIcon />
        </IconButton>
        <Typography variant="subtitle1" sx={{ flexGrow: 1, fontWeight: 600 }} noWrap>
          {t('app.tagline')}
        </Typography>
        <RealtimeIndicator />
        <NotificationBell />
        <Box>
          <IconButton onClick={(e) => setAnchor(e.currentTarget)} color="inherit" data-testid="user-menu">
            <Avatar sx={{ width: 32, height: 32, bgcolor: 'secondary.main', fontSize: 14 }}>
              {initials}
            </Avatar>
          </IconButton>
          <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
            <Box sx={{ px: 2, py: 1 }}>
              <Typography variant="subtitle2">
                {user?.first_name} {user?.last_name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {user?.email}
              </Typography>
              <Box sx={{ mt: 0.5 }}>
                <Chip
                  size="small"
                  label={user ? t(`roles.${user.role}`) : ''}
                  color="primary"
                  variant="outlined"
                />
              </Box>
              {user?.role === 'COUNTRY_REGULATORY' && (
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                  {user.countries.join(', ')}
                </Typography>
              )}
            </Box>
            <Divider />
            <MenuItem
              onClick={() => {
                setAnchor(null);
                logout.mutate(undefined, { onSettled: () => navigate('/login') });
              }}
            >
              <ListItemIcon>
                <LogoutIcon fontSize="small" />
              </ListItemIcon>
              {t('nav.logout')}
            </MenuItem>
          </Menu>
        </Box>
      </Toolbar>
    </AppBar>
  );
}
