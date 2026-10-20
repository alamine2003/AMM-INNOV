import { create } from 'zustand';

/** Menu latéral réduit aux icônes (écrans larges) : préférence gardée dans ce navigateur. */
const KEY = 'amm-gh.sidebar';

export const DRAWER_WIDTH = 240;
export const DRAWER_COLLAPSED_WIDTH = 64;

function stored(): boolean {
  try {
    return localStorage.getItem(KEY) === 'collapsed';
  } catch {
    return false;
  }
}

interface SidebarState {
  collapsed: boolean;
  toggle: () => void;
}

export const useSidebarStore = create<SidebarState>((set, get) => ({
  collapsed: stored(),
  toggle: () => {
    const collapsed = !get().collapsed;
    try {
      localStorage.setItem(KEY, collapsed ? 'collapsed' : 'open');
    } catch {
      // stockage indisponible (navigation privée) : la préférence vaut pour la session
    }
    set({ collapsed });
  },
}));

/** Largeur du menu sur grand écran, selon qu'il est réduit ou non. */
export function useDrawerWidth(): number {
  return useSidebarStore((s) => (s.collapsed ? DRAWER_COLLAPSED_WIDTH : DRAWER_WIDTH));
}
