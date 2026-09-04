import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';
import { lazy, Suspense } from 'react';
import { Box, CircularProgress } from '@mui/material';
import { AppLayout } from './layout/AppLayout';
import { RequireAuth, RequireRole } from './guards';
import { NotFoundPage } from '@/components/NotFoundPage';

const LoginPage = lazy(() => import('@/features/auth/LoginPage'));
const AfricaDashboardPage = lazy(() => import('@/features/dashboard/AfricaDashboardPage'));
const CountryDashboardPage = lazy(() => import('@/features/dashboard/CountryDashboardPage'));
const AmmListPage = lazy(() => import('@/features/amm/AmmListPage'));
const AmmDetailPage = lazy(() => import('@/features/amm/AmmDetailPage'));
const AlertsPage = lazy(() => import('@/features/alerts/AlertsPage'));
const DocumentsLibraryPage = lazy(() => import('@/features/documents/DocumentsLibraryPage'));
const ProductsPage = lazy(() => import('@/features/catalog/ProductsPage'));
const ProductDetailPage = lazy(() => import('@/features/catalog/ProductDetailPage'));
const UsersAdminPage = lazy(() => import('@/features/admin/UsersAdminPage'));
const CountriesAdminPage = lazy(() => import('@/features/admin/CountriesAdminPage'));
const RangesAdminPage = lazy(() => import('@/features/admin/RangesAdminPage'));
const AlertRulesAdminPage = lazy(() => import('@/features/admin/AlertRulesAdminPage'));
const ImportsPage = lazy(() => import('@/features/imports/ImportsPage'));
const ImportDetailPage = lazy(() => import('@/features/imports/ImportDetailPage'));

const Fallback = () => (
  <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
    <CircularProgress />
  </Box>
);

const page = (element: React.ReactNode) => <Suspense fallback={<Fallback />}>{element}</Suspense>;

export const routes: RouteObject[] = [
  { path: '/login', element: page(<LoginPage />) },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: page(<AfricaDashboardPage />) },
          { path: 'countries/:iso2', element: page(<CountryDashboardPage />) },
          { path: 'amms', element: page(<AmmListPage />) },
          { path: 'amms/:id', element: page(<AmmDetailPage />) },
          { path: 'renewals/:renewalId', element: page(<AmmDetailPage />) },
          { path: 'alerts', element: page(<AlertsPage />) },
          { path: 'documents', element: page(<DocumentsLibraryPage />) },
          { path: 'products', element: page(<ProductsPage />) },
          { path: 'products/:id', element: page(<ProductDetailPage />) },
          {
            path: 'admin',
            element: <RequireRole roles={['CEO_ADMIN', 'HQ_REGULATORY']} />,
            children: [
              { index: true, element: <Navigate to="/admin/users" replace /> },
              { path: 'users', element: page(<UsersAdminPage />) },
              { path: 'countries', element: page(<CountriesAdminPage />) },
              { path: 'ranges', element: page(<RangesAdminPage />) },
              { path: 'alert-rules', element: page(<AlertRulesAdminPage />) },
              { path: 'imports', element: page(<ImportsPage />) },
              { path: 'imports/:id', element: page(<ImportDetailPage />) },
            ],
          },
          { path: 'imports/:id', element: page(<ImportDetailPage />) },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

export const createAppRouter = () => createBrowserRouter(routes);
