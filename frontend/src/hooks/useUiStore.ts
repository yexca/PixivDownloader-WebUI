import { create } from "zustand";

import { applyThemeMode, getStoredThemeMode, storeThemeMode, type ThemeMode } from "@/lib/theme";

type UiState = {
  sidebarOpen: boolean;
  themeMode: ThemeMode;
  setSidebarOpen: (open: boolean) => void;
  setThemeMode: (mode: ThemeMode) => void;
};

const initialThemeMode = getStoredThemeMode();
applyThemeMode(initialThemeMode);

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: false,
  themeMode: initialThemeMode,
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  setThemeMode: (themeMode) => {
    storeThemeMode(themeMode);
    applyThemeMode(themeMode);
    set({ themeMode });
  }
}));
