export type ColorScheme = "light" | "dark";
export type ThemePresetSource = "system" | "user";

export type ThemeTokens = {
  background: string;
  foreground: string;
  card: string;
  cardForeground: string;
  primary: string;
  primaryForeground: string;
  secondary: string;
  secondaryForeground: string;
  muted: string;
  mutedForeground: string;
  accent: string;
  accentForeground: string;
  destructive: string;
  destructiveForeground: string;
  success: string;
  successMuted: string;
  successForeground: string;
  warning: string;
  warningMuted: string;
  warningForeground: string;
  border: string;
  input: string;
  ring: string;
};

export type ThemeBackground = {
  type: "none" | "image";
  imageUrl: string;
  opacity: number;
  dim: number;
  blur: number;
};

export type ThemePreset = {
  id: string;
  name: string;
  scheme: ColorScheme;
  source: ThemePresetSource;
  readonly: boolean;
  tokens: ThemeTokens;
  background: ThemeBackground;
};

export type AppearanceSettings = {
  followSystem: boolean;
  activePresetId: string;
  systemLightPresetId: string;
  systemDarkPresetId: string;
};

export type StoredAppearance = {
  settings: AppearanceSettings;
  customPresets: ThemePreset[];
};

const appearanceStorageKey = "pixiv-downloader-appearance";
const legacyThemeStorageKey = "pixiv-downloader-theme-mode";
const darkMediaQuery = "(prefers-color-scheme: dark)";

const defaultBackground: ThemeBackground = {
  type: "none",
  imageUrl: "",
  opacity: 0.18,
  dim: 0.35,
  blur: 0
};

const lightTokens: ThemeTokens = {
  background: "0 0% 98%",
  foreground: "222 18% 15%",
  card: "0 0% 100%",
  cardForeground: "222 18% 15%",
  primary: "207 80% 40%",
  primaryForeground: "0 0% 100%",
  secondary: "162 23% 91%",
  secondaryForeground: "166 35% 18%",
  muted: "220 14% 93%",
  mutedForeground: "218 11% 42%",
  accent: "46 88% 88%",
  accentForeground: "38 72% 24%",
  destructive: "0 72% 44%",
  destructiveForeground: "0 0% 100%",
  success: "153 62% 34%",
  successMuted: "150 64% 94%",
  successForeground: "153 55% 19%",
  warning: "37 92% 42%",
  warningMuted: "48 96% 89%",
  warningForeground: "32 82% 22%",
  border: "220 13% 86%",
  input: "220 13% 82%",
  ring: "207 80% 40%"
};

const darkTokens: ThemeTokens = {
  background: "222 24% 10%",
  foreground: "210 26% 92%",
  card: "222 22% 13%",
  cardForeground: "210 26% 92%",
  primary: "205 88% 62%",
  primaryForeground: "222 38% 10%",
  secondary: "194 30% 20%",
  secondaryForeground: "180 34% 88%",
  muted: "222 18% 18%",
  mutedForeground: "215 14% 68%",
  accent: "42 57% 24%",
  accentForeground: "43 85% 88%",
  destructive: "0 70% 58%",
  destructiveForeground: "0 0% 100%",
  success: "153 62% 48%",
  successMuted: "154 30% 17%",
  successForeground: "149 70% 86%",
  warning: "39 92% 56%",
  warningMuted: "39 42% 18%",
  warningForeground: "42 84% 86%",
  border: "221 16% 24%",
  input: "221 16% 30%",
  ring: "205 88% 62%"
};

export const builtinThemePresets: ThemePreset[] = [
  {
    id: "light",
    name: "Light",
    scheme: "light",
    source: "system",
    readonly: true,
    tokens: lightTokens,
    background: defaultBackground
  },
  {
    id: "dark",
    name: "Dark",
    scheme: "dark",
    source: "system",
    readonly: true,
    tokens: darkTokens,
    background: defaultBackground
  },
  {
    id: "pixiv-light",
    name: "Pixiv Light",
    scheme: "light",
    source: "system",
    readonly: true,
    tokens: {
      ...lightTokens,
      primary: "207 88% 48%",
      secondary: "197 78% 93%",
      secondaryForeground: "204 80% 24%",
      accent: "328 86% 93%",
      accentForeground: "329 68% 30%",
      ring: "207 88% 48%"
    },
    background: defaultBackground
  },
  {
    id: "pixiv-dark",
    name: "Pixiv Dark",
    scheme: "dark",
    source: "system",
    readonly: true,
    tokens: {
      ...darkTokens,
      background: "224 28% 9%",
      card: "224 24% 12%",
      primary: "204 92% 64%",
      secondary: "211 35% 19%",
      secondaryForeground: "202 74% 88%",
      accent: "327 38% 22%",
      accentForeground: "329 78% 88%",
      ring: "204 92% 64%"
    },
    background: defaultBackground
  }
];

export const defaultAppearanceSettings: AppearanceSettings = {
  followSystem: true,
  activePresetId: "light",
  systemLightPresetId: "light",
  systemDarkPresetId: "dark"
};

export function getStoredAppearance(): StoredAppearance {
  if (typeof window === "undefined") {
    return { settings: defaultAppearanceSettings, customPresets: [] };
  }
  const fallback = legacyAppearance();
  try {
    const raw = window.localStorage.getItem(appearanceStorageKey);
    if (!raw) {
      return fallback;
    }
    const parsed = JSON.parse(raw) as Partial<StoredAppearance>;
    return normalizeStoredAppearance(parsed, fallback);
  } catch {
    return fallback;
  }
}

export function storeAppearance(appearance: StoredAppearance): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(appearanceStorageKey, JSON.stringify(appearance));
  } catch {
    // Appearance persistence is a convenience; rendering should still continue.
  }
}

export function allThemePresets(customPresets: ThemePreset[]): ThemePreset[] {
  return [...builtinThemePresets, ...customPresets];
}

export function resolveThemePreset(settings: AppearanceSettings, presets: ThemePreset[]): ThemePreset {
  const scheme = systemColorScheme();
  const id = settings.followSystem
    ? scheme === "dark"
      ? settings.systemDarkPresetId
      : settings.systemLightPresetId
    : settings.activePresetId;
  const preset = presets.find((item) => item.id === id);
  return preset ?? builtinThemePresets.find((item) => item.id === (scheme === "dark" ? "dark" : "light"))!;
}

export function applyThemePreset(preset: ThemePreset): void {
  if (typeof document === "undefined") {
    return;
  }
  const root = document.documentElement;
  root.classList.toggle("dark", preset.scheme === "dark");
  root.style.colorScheme = preset.scheme;
  setCssVar(root, "background", preset.tokens.background);
  setCssVar(root, "foreground", preset.tokens.foreground);
  setCssVar(root, "card", preset.tokens.card);
  setCssVar(root, "card-foreground", preset.tokens.cardForeground);
  setCssVar(root, "primary", preset.tokens.primary);
  setCssVar(root, "primary-foreground", preset.tokens.primaryForeground);
  setCssVar(root, "secondary", preset.tokens.secondary);
  setCssVar(root, "secondary-foreground", preset.tokens.secondaryForeground);
  setCssVar(root, "muted", preset.tokens.muted);
  setCssVar(root, "muted-foreground", preset.tokens.mutedForeground);
  setCssVar(root, "accent", preset.tokens.accent);
  setCssVar(root, "accent-foreground", preset.tokens.accentForeground);
  setCssVar(root, "destructive", preset.tokens.destructive);
  setCssVar(root, "destructive-foreground", preset.tokens.destructiveForeground);
  setCssVar(root, "success", preset.tokens.success);
  setCssVar(root, "success-muted", preset.tokens.successMuted);
  setCssVar(root, "success-foreground", preset.tokens.successForeground);
  setCssVar(root, "warning", preset.tokens.warning);
  setCssVar(root, "warning-muted", preset.tokens.warningMuted);
  setCssVar(root, "warning-foreground", preset.tokens.warningForeground);
  setCssVar(root, "border", preset.tokens.border);
  setCssVar(root, "input", preset.tokens.input);
  setCssVar(root, "ring", preset.tokens.ring);
  root.style.setProperty("--app-background-image", preset.background.type === "image" ? `url("${cssUrl(preset.background.imageUrl)}")` : "none");
  root.style.setProperty("--app-background-opacity", String(preset.background.opacity));
  root.style.setProperty("--app-background-dim", String(preset.background.dim));
  root.style.setProperty("--app-background-blur", `${preset.background.blur}px`);
}

export function watchSystemTheme(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => undefined;
  }
  const media = window.matchMedia(darkMediaQuery);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

export function createUserPreset(base: ThemePreset, values: Partial<ThemePreset> = {}): ThemePreset {
  return {
    ...base,
    ...values,
    id: values.id ?? `custom-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    name: values.name ?? `${base.name} Copy`,
    source: "user",
    readonly: false,
    tokens: { ...base.tokens, ...values.tokens },
    background: { ...base.background, ...values.background }
  };
}

function normalizeStoredAppearance(value: Partial<StoredAppearance>, fallback: StoredAppearance): StoredAppearance {
  const customPresets = Array.isArray(value.customPresets)
    ? value.customPresets.filter(isThemePreset).map((preset) => ({ ...preset, source: "user" as const, readonly: false }))
    : fallback.customPresets;
  const presets = allThemePresets(customPresets);
  const settings = normalizeSettings(value.settings, fallback.settings, presets);
  return { settings, customPresets };
}

function normalizeSettings(
  value: Partial<AppearanceSettings> | undefined,
  fallback: AppearanceSettings,
  presets: ThemePreset[]
): AppearanceSettings {
  return {
    followSystem: typeof value?.followSystem === "boolean" ? value.followSystem : fallback.followSystem,
    activePresetId: validPresetId(value?.activePresetId, presets) ?? fallback.activePresetId,
    systemLightPresetId: validPresetId(value?.systemLightPresetId, presets, "light") ?? fallback.systemLightPresetId,
    systemDarkPresetId: validPresetId(value?.systemDarkPresetId, presets, "dark") ?? fallback.systemDarkPresetId
  };
}

function legacyAppearance(): StoredAppearance {
  if (typeof window === "undefined") {
    return { settings: defaultAppearanceSettings, customPresets: [] };
  }
  const mode = window.localStorage.getItem(legacyThemeStorageKey);
  if (mode === "light") {
    return { settings: { ...defaultAppearanceSettings, followSystem: false, activePresetId: "light" }, customPresets: [] };
  }
  if (mode === "dark") {
    return { settings: { ...defaultAppearanceSettings, followSystem: false, activePresetId: "dark" }, customPresets: [] };
  }
  return { settings: defaultAppearanceSettings, customPresets: [] };
}

function validPresetId(value: unknown, presets: ThemePreset[], scheme?: ColorScheme): string | null {
  if (typeof value !== "string") {
    return null;
  }
  return presets.some((preset) => preset.id === value && (!scheme || preset.scheme === scheme)) ? value : null;
}

function isThemePreset(value: unknown): value is ThemePreset {
  if (!value || typeof value !== "object") {
    return false;
  }
  const preset = value as Partial<ThemePreset>;
  return (
    typeof preset.id === "string" &&
    typeof preset.name === "string" &&
    (preset.scheme === "light" || preset.scheme === "dark") &&
    Boolean(preset.tokens) &&
    Boolean(preset.background)
  );
}

function systemColorScheme(): ColorScheme {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "light";
  }
  return window.matchMedia(darkMediaQuery).matches ? "dark" : "light";
}

function setCssVar(root: HTMLElement, name: string, value: string): void {
  root.style.setProperty(`--${name}`, value);
}

function cssUrl(value: string): string {
  return value.replaceAll("\\", "\\\\").replaceAll('"', '\\"');
}
