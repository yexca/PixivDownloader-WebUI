import { create } from "zustand";

import {
  allThemePresets,
  applyThemePreset,
  createUserPreset,
  getStoredAppearance,
  resolveThemePreset,
  storeAppearance,
  type AppearanceSettings,
  type ColorScheme,
  type ThemePreset
} from "@/lib/theme";

type UiState = {
  sidebarOpen: boolean;
  appearanceSettings: AppearanceSettings;
  customThemePresets: ThemePreset[];
  activeThemePreset: ThemePreset;
  setSidebarOpen: (open: boolean) => void;
  setFollowSystemTheme: (followSystem: boolean) => void;
  setActiveThemePreset: (presetId: string) => void;
  setSystemThemePreset: (scheme: ColorScheme, presetId: string) => void;
  createThemePreset: (basePresetId: string, name?: string) => void;
  updateThemePreset: (preset: ThemePreset) => void;
  deleteThemePreset: (presetId: string) => void;
  refreshResolvedTheme: () => void;
};

const initialAppearance = getStoredAppearance();
const initialPresets = allThemePresets(initialAppearance.customPresets);
const initialActivePreset = resolveThemePreset(initialAppearance.settings, initialPresets);
applyThemePreset(initialActivePreset);

function persistAndApply(settings: AppearanceSettings, customPresets: ThemePreset[]) {
  const presets = allThemePresets(customPresets);
  const activeThemePreset = resolveThemePreset(settings, presets);
  storeAppearance({ settings, customPresets });
  applyThemePreset(activeThemePreset);
  return { appearanceSettings: settings, customThemePresets: customPresets, activeThemePreset };
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: false,
  appearanceSettings: initialAppearance.settings,
  customThemePresets: initialAppearance.customPresets,
  activeThemePreset: initialActivePreset,
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  setFollowSystemTheme: (followSystem) =>
    set((state) => persistAndApply({ ...state.appearanceSettings, followSystem }, state.customThemePresets)),
  setActiveThemePreset: (activePresetId) =>
    set((state) => persistAndApply({ ...state.appearanceSettings, activePresetId, followSystem: false }, state.customThemePresets)),
  setSystemThemePreset: (scheme, presetId) =>
    set((state) =>
      persistAndApply(
        {
          ...state.appearanceSettings,
          [scheme === "dark" ? "systemDarkPresetId" : "systemLightPresetId"]: presetId
        },
        state.customThemePresets
      )
    ),
  createThemePreset: (basePresetId, name) =>
    set((state) => {
      const base = allThemePresets(state.customThemePresets).find((preset) => preset.id === basePresetId) ?? state.activeThemePreset;
      const nextPreset = createUserPreset(base, { name });
      const customPresets = [...state.customThemePresets, nextPreset];
      return persistAndApply({ ...state.appearanceSettings, activePresetId: nextPreset.id, followSystem: false }, customPresets);
    }),
  updateThemePreset: (preset) =>
    set((state) => {
      const customPresets = state.customThemePresets.map((item) => (item.id === preset.id ? { ...preset, source: "user", readonly: false } : item));
      return persistAndApply(state.appearanceSettings, customPresets);
    }),
  deleteThemePreset: (presetId) =>
    set((state) => {
      const customPresets = state.customThemePresets.filter((preset) => preset.id !== presetId);
      const settings = {
        ...state.appearanceSettings,
        activePresetId: state.appearanceSettings.activePresetId === presetId ? "light" : state.appearanceSettings.activePresetId,
        systemLightPresetId:
          state.appearanceSettings.systemLightPresetId === presetId ? "light" : state.appearanceSettings.systemLightPresetId,
        systemDarkPresetId:
          state.appearanceSettings.systemDarkPresetId === presetId ? "dark" : state.appearanceSettings.systemDarkPresetId
      };
      return persistAndApply(settings, customPresets);
    }),
  refreshResolvedTheme: () =>
    set((state) => {
      const activeThemePreset = resolveThemePreset(state.appearanceSettings, allThemePresets(state.customThemePresets));
      applyThemePreset(activeThemePreset);
      return { activeThemePreset };
    })
}));
