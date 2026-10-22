import {
  Box,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ListSubheader,
  Toolbar,
  Tooltip,
} from '@mui/material';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
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
import MenuBookIcon from '@mui/icons-material/MenuBook';
import AssignmentTurnedInIcon from '@mui/icons-material/AssignmentTurnedIn';
import { NavLink, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/features/auth/authStore';
import { BrandLogo } from '@/components/BrandLogo';
import { navItemsForRole, type NavItem } from './navigation';
import { DRAWER_WIDTH, useDrawerWidth, useSidebarStore } from './sidebarStore';

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
  binders: <MenuBookIcon />,
  deposits: <AssignmentTurnedInIcon />,
};

/** `collapsed` : icônes seules (le libellé passe en info-bulle), pour laisser la place au contenu. */
function NavList({ collapsed = false }: { collapsed?: boolean }) {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const location = useLocation();
  const items = navItemsForRole(user?.role);
  const main = items.filter((i) => !i.section);
  const admin = items.filter((i) => i.section === 'admin');
  const isActive = (to: string) =>
    to === '/' ? location.pathname === '/' : location.pathname.startsWith(to);
  const render = (item: NavItem) => {
    const label = t(item.labelKey);
    const button = (
      <ListItemButton
        key={item.key}
        component={NavLink}
        to={item.to}
        selected={isActive(item.to)}
        aria-label={collapsed ? label : undefined}
        sx={{
          borderRadius: 1,
          mx: 1,
          my: 0.25,
          justifyContent: collapsed ? 'center' : 'flex-start',
          px: collapsed ? 1 : 2,
        }}
        data-testid={`nav-${item.key}`}
      >
        <ListItemIcon sx={{ minWidth: collapsed ? 0 : 36, justifyContent: 'center' }}>
          {ICONS[item.icon]}
        </ListItemIcon>
        {!collapsed && <ListItemText primary={label} />}
      </ListItemButton>
    );
    return collapsed ? (
      <Tooltip key={item.key} title={label} placement="right">
        {button}
      </Tooltip>
    ) : (
      button
    );
  };
  return (
    <Box sx={{ overflowX: 'hidden', overflowY: 'auto', flexGrow: 1 }}>
      <Toolbar sx={{ justifyContent: collapsed ? 'center' : 'flex-start', px: collapsed ? 1 : 2 }}>
        <BrandLogo height={collapsed ? 15 : 28} />
      </Toolbar>
      <Divider />
      <List dense>{main.map(render)}</List>
      {admin.length > 0 && (
        <>
          <Divider />
          <List
            dense
            subheader={collapsed ? undefined : <ListSubheader disableSticky>{t('nav.admin')}</ListSubheader>}
          >
            {admin.map(render)}
          </List>
        </>
      )}
    </Box>
  );
}

/** Bas du menu : réduire aux icônes, ou rouvrir. */
function CollapseToggle() {
  const { t } = useTranslation();
  const collapsed = useSidebarStore((s) => s.collapsed);
  const toggle = useSidebarStore((s) => s.toggle);
  const label = t(collapsed ? 'nav.expand' : 'nav.collapse');
  return (
    <Box
      sx={{
        borderTop: 1,
        borderColor: 'divider',
        display: 'flex',
        justifyContent: collapsed ? 'center' : 'flex-end',
        p: 0.5,
      }}
    >
      <Tooltip title={label} placement="right">
        <IconButton onClick={toggle} aria-label={label} size="small" data-testid="sidebar-toggle">
          {collapsed ? <ChevronRightIcon /> : <ChevronLeftIcon />}
        </IconButton>
      </Tooltip>
    </Box>
  );
}

export function SideNav({ mobileOpen, onClose }: { mobileOpen: boolean; onClose: () => void }) {
  const collapsed = useSidebarStore((s) => s.collapsed);
  const width = useDrawerWidth();
  const transition = 'width 200ms ease';
  return (
    <Box component="nav" sx={{ width: { md: width }, flexShrink: { md: 0 }, transition }}>
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
          '& .MuiDrawer-paper': {
            width,
            boxSizing: 'border-box',
            overflowX: 'hidden',
            transition,
            display: 'flex',
            flexDirection: 'column',
          },
        }}
        data-testid="sidebar"
        data-collapsed={collapsed ? 'true' : 'false'}
      >
        <NavList collapsed={collapsed} />
        <CollapseToggle />
      </Drawer>
    </Box>
  );
}
