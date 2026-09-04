import { useState } from 'react';
import { Outlet } from 'react-router';
import { Box, Toolbar } from '@mui/material';
import { useRealtime } from '@/realtime/useRealtime';
import { TopBar } from './TopBar';
import { SideNav, DRAWER_WIDTH } from './SideNav';

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  useRealtime(true);
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <TopBar onMenuClick={() => setMobileOpen((o) => !o)} />
      <SideNav mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: { xs: 2, md: 3 },
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          minWidth: 0,
        }}
      >
        <Toolbar />
        <Outlet />
      </Box>
    </Box>
  );
}
