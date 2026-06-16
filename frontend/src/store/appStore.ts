import { create } from 'zustand';

interface BreadcrumbItem {
  title: string;
  path?: string;
}

interface AppState {
  theme: 'light' | 'dark';
  sidebarCollapsed: boolean;
  breadcrumbs: BreadcrumbItem[];

  toggleTheme: () => void;
  setTheme: (theme: 'light' | 'dark') => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setBreadcrumbs: (breadcrumbs: BreadcrumbItem[]) => void;
}

export const useAppStore = create<AppState>((set) => ({
  theme: (localStorage.getItem('llm-platform-theme') as 'light' | 'dark') || 'light',
  sidebarCollapsed: false,
  breadcrumbs: [],

  toggleTheme: () =>
    set((state) => {
      const nextTheme = state.theme === 'light' ? 'dark' : 'light';
      localStorage.setItem('llm-platform-theme', nextTheme);
      return { theme: nextTheme };
    }),

  setTheme: (theme: 'light' | 'dark') => {
    localStorage.setItem('llm-platform-theme', theme);
    set({ theme });
  },

  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  setSidebarCollapsed: (collapsed: boolean) =>
    set({ sidebarCollapsed: collapsed }),

  setBreadcrumbs: (breadcrumbs: BreadcrumbItem[]) =>
    set({ breadcrumbs }),
}));
