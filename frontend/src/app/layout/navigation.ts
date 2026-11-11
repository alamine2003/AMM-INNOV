import type { Role, User, UserAction } from '@/api/types';
import { can } from '@/features/auth/authStore';

export interface NavItem {
  key: string;
  labelKey: string;
  to: string;
  roles?: Role[];
  /** Droit réglable par le CEO : l'entrée suit le droit, pas le rôle. */
  action?: UserAction;
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
    | 'imports'
    | 'binders'
    | 'deposits'
    | 'trash'
    | 'audit'
    | 'permissions'
    | 'errors';
  section?: 'admin';
}

export const NAV_ITEMS: NavItem[] = [
  { key: 'dashboard', labelKey: 'nav.dashboard', to: '/', icon: 'dashboard' },
  { key: 'amms', labelKey: 'nav.amms', to: '/amms', icon: 'amms' },
  { key: 'alerts', labelKey: 'nav.alerts', to: '/alerts', icon: 'alerts' },
  { key: 'documents', labelKey: 'nav.documents', to: '/documents', icon: 'documents' },
  { key: 'dossier-imports', labelKey: 'nav.dossierImports', to: '/dossier-imports', icon: 'imports' },
  { key: 'deposits', labelKey: 'nav.deposits', to: '/depots', icon: 'deposits' },
  { key: 'binders', labelKey: 'nav.binders', to: '/classeurs', icon: 'binders' },
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
  {
    key: 'trash',
    labelKey: 'nav.trash',
    to: '/admin/corbeille',
    icon: 'trash',
    action: 'trash.restore',
    section: 'admin',
  },
  {
    key: 'audit',
    labelKey: 'nav.audit',
    to: '/admin/audit',
    icon: 'audit',
    action: 'audit.view',
    section: 'admin',
  },
  {
    key: 'errors',
    labelKey: 'nav.errors',
    to: '/admin/erreurs',
    icon: 'errors',
    action: 'errors.view',
    section: 'admin',
  },
  {
    key: 'permissions',
    labelKey: 'nav.permissions',
    to: '/admin/permissions',
    icon: 'permissions',
    action: 'permissions.manage',
    section: 'admin',
  },
];

export function navItemsForRole(role: Role | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.action && (!item.roles || (role && item.roles.includes(role))));
}

/** Entrées du menu pour l'utilisateur connecté : par rôle, ou par droit réglé par le CEO. */
export function navItemsFor(user: User | null): NavItem[] {
  return NAV_ITEMS.filter((item) => {
    if (item.action) return can(user, item.action);
    return !item.roles || (!!user && item.roles.includes(user.role));
  });
}
