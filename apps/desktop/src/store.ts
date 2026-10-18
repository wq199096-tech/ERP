import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface Session {
  token: string;
  userName: string;
  tenantName: string;
}

interface AppState {
  session: Session | null;
  activeMenu: string;
  selectedShop: string;
  setSession: (session: Session | null) => void;
  setActiveMenu: (key: string) => void;
  setSelectedShop: (id: string) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      session: null,
      activeMenu: 'dashboard',
      selectedShop: '',
      setSession: (session) => set({ session }),
      setActiveMenu: (activeMenu) => set({ activeMenu }),
      setSelectedShop: (selectedShop) => set({ selectedShop }),
    }),
    { name: 'smartorder-session' },
  ),
);

