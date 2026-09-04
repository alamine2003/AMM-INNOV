import type { Role } from '@/api/types';

export interface NavItem {
  key: string;
  labelKey: string;
  to: string;
  roles?: Role[];
  icon:
    | 'dashboard'
    | 'amms'
    | 'alerts'
    | 'documents'
    | 'products'
    | 'users'
    | 'countries'
    | 'ranges'
    | 'rules'
    | 'imports';
  section?: 'admin';
}

export const NAV_ITEMS: NavItem[] = [
  { key: 'dashboard', labelKey: 'nav.dashboard', to: '/', icon: 'dashboard' },
  { key: 'amms', labelKey: 'nav.amms', to: '/amms', icon: 'amms' },
  { key: 'alerts', labelKey: 'nav.alerts', to: '/alerts', icon: 'alerts' },
  { key: 'documents', labelKey: 'nav.documents', to: '/documents', icon: 'documents' },
  { key: 'products', labelKey: 'nav.products', to: '/products', icon: 'products' },
  {
    key: 'users',
    labelKey: 'nav.users',
    to: '/admin/users',
    icon: 'users',
    roles: ['CEO_ADMIN', 'HQ_REGULATORY'],
    section: 'admin',
  },
  {
    key: 'countries',
    labelKey: 'nav.countries',
    to: '/admin/countries',
    icon: 'countries',
    roles: ['CEO_ADMIN', 'HQ_REGULATORY'],
    section: 'admin',
  },
  {
    key: 'ranges',
    labelKey: 'nav.ranges',
    to: '/admin/ranges',
    icon: 'ranges',
    roles: ['CEO_ADMIN', 'HQ_REGULATORY'],
    section: 'admin',
  },
  {
    key: 'rules',
    labelKey: 'nav.alertRules',
    to: '/admin/alert-rules',
    icon: 'rules',
    roles: ['CEO_ADMIN', 'HQ_REGULATORY'],
    section: 'admin',
  },
  {
    key: 'imports',
    labelKey: 'nav.imports',
    to: '/admin/imports',
    icon: 'imports',
    roles: ['CEO_ADMIN', 'HQ_REGULATORY'],
    section: 'admin',
  },
];

export function navItemsForRole(role: Role | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.roles || (role && item.roles.includes(role)));
}
