export type ThemeMode = "system" | "light" | "dark";

const themeStorageKey = "pixiv-downloader-theme-mode";
const darkMediaQuery = "(prefers-color-scheme: dark)";

export function getStoredThemeMode(): ThemeMode {
  if (typeof window === "undefined") {
    return "system";
  }
  try {
    const value = window.localStorage.getItem(themeStorageKey);
    return isThemeMode(value) ? value : "system";
  } catch {
    return "system";
  }
}

export function storeThemeMode(mode: ThemeMode): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(themeStorageKey, mode);
  } catch {
    // Theme persistence is a convenience; rendering should still continue.
  }
}

export function applyThemeMode(mode: ThemeMode): void {
  if (typeof document === "undefined" || typeof window === "undefined") {
    return;
  }
  const prefersDark = typeof window.matchMedia === "function" && window.matchMedia(darkMediaQuery).matches;
  const useDark = mode === "dark" || (mode === "system" && prefersDark);
  document.documentElement.classList.toggle("dark", useDark);
  document.documentElement.style.colorScheme = useDark ? "dark" : "light";
}

export function watchSystemTheme(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => undefined;
  }
  const media = window.matchMedia(darkMediaQuery);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

function isThemeMode(value: string | null): value is ThemeMode {
  return value === "system" || value === "light" || value === "dark";
}
