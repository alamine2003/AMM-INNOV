import {
  Box,
  Divider,
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ListSubheader,
  Toolbar,
  Typography,
} from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import TableChartIcon from '@mui/icons-material/TableChart';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import FolderIcon from '@mui/icons-material/Folder';
import MedicationIcon from '@mui/icons-material/Medication';
import PeopleIcon from '@mui/icons-material/People';
import PublicIcon from '@mui/icons-material/Public';
import CategoryIcon from '@mui/icons-material/Category';
import RuleIcon from '@mui/icons-material/Rule';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import { NavLink, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/features/auth/authStore';
import { navItemsForRole, type NavItem } from './navigation';

export const DRAWER_WIDTH = 240;

const ICONS: Record<NavItem['icon'], React.ReactNode> = {
  dashboard: <DashboardIcon />,
  amms: <TableChartIcon />,
  alerts: <NotificationsActiveIcon />,
  documents: <FolderIcon />,
  products: <MedicationIcon />,
  users: <PeopleIcon />,
  countries: <PublicIcon />,
  ranges: <CategoryIcon />,
  rules: <RuleIcon />,
  imports: <UploadFileIcon />,
};

function NavList() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const location = useLocation();
  const items = navItemsForRole(user?.role);
  const main = items.filter((i) => !i.section);
  const admin = items.filter((i) => i.section === 'admin');
  const isActive = (to: string) =>
    to === '/' ? location.pathname === '/' : location.pathname.startsWith(to);
  const render = (item: NavItem) => (
    <ListItemButton
      key={item.key}
      component={NavLink}
      to={item.to}
      selected={isActive(item.to)}
      sx={{ borderRadius: 1, mx: 1, my: 0.25 }}
      data-testid={`nav-${item.key}`}
    >
      <ListItemIcon sx={{ minWidth: 36 }}>{ICONS[item.icon]}</ListItemIcon>
      <ListItemText primary={t(item.labelKey)} />
    </ListItemButton>
  );
  return (
    <Box sx={{ overflow: 'auto' }}>
      <Toolbar>
        <Typography variant="h6" color="primary" sx={{ fontWeight: 800 }}>
          {t('app.name')}
        </Typography>
      </Toolbar>
      <Divider />
      <List dense>{main.map(render)}</List>
      {admin.length > 0 && (
        <>
          <Divider />
          <List dense subheader={<ListSubheader disableSticky>{t('nav.admin')}</ListSubheader>}>
            {admin.map(render)}
          </List>
        </>
      )}
    </Box>
  );
}

export function SideNav({ mobileOpen, onClose }: { mobileOpen: boolean; onClose: () => void }) {
  return (
    <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }}>
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={onClose}
        ModalProps={{ keepMounted: true }}
        sx={{ display: { xs: 'block', md: 'none' }, '& .MuiDrawer-paper': { width: DRAWER_WIDTH } }}
      >
        <NavList />
      </Drawer>
      <Drawer
        variant="permanent"
        open
        sx={{
          display: { xs: 'none', md: 'block' },
          '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' },
        }}
      >
        <NavList />
      </Drawer>
    </Box>
  );
}
