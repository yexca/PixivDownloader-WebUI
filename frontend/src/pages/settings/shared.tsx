import type React from "react";

import type { PixivBrowserAuthServiceStatusResponse, SettingsResponse, SettingsUpdateRequest } from "@/api/settings";
import { Input } from "@/components/ui/input";

export type SettingsTab = "basic" | "pixiv" | "appearance" | "advanced";

export type BasicForm = Pick<
  SettingsUpdateRequest,
  | "download_path"
  | "request_base_delay_seconds"
  | "request_random_delay_seconds"
  | "file_download_base_delay_seconds"
  | "file_download_random_delay_seconds"
  | "max_concurrent_downloads"
  | "max_active_workflow_triggers"
  | "max_active_run_jobs"
  | "min_free_space_gb"
  | "library_stale_check_days"
  | "existing_file_behavior"
>;

export type TestStatusState = "unconfigured" | "untested" | "checking" | "valid" | "invalid";

export type TestStatus = {
  state: TestStatusState;
  message: string;
  checkedAt?: Date;
};

export type AuthBrowserDialog = {
  type: "start" | "stop";
  status: PixivBrowserAuthServiceStatusResponse;
};

export function notConfiguredAuthStatus(): TestStatus {
  return { state: "unconfigured", message: "No Pixiv refresh token is configured." };
}

export function untestedAuthStatus(): TestStatus {
  return { state: "untested", message: "A Pixiv refresh token is saved. Run Test Auth when you want to verify it." };
}

export function notConfiguredConnectionStatus(): TestStatus {
  return { state: "unconfigured", message: "No Pixiv refresh token is configured." };
}

export function untestedConnectionStatus(): TestStatus {
  return {
    state: "untested",
    message: "A real Pixiv API request has not been tested in this session."
  };
}

export function resetTestStatuses(
  configured: boolean,
  setAuthTestStatus: (status: TestStatus) => void,
  setConnectionTestStatus: (status: TestStatus) => void
): void {
  if (configured) {
    setAuthTestStatus(untestedAuthStatus());
    setConnectionTestStatus(untestedConnectionStatus());
  } else {
    setAuthTestStatus(notConfiguredAuthStatus());
    setConnectionTestStatus(notConfiguredConnectionStatus());
  }
}

export function formatCheckedAt(value: Date): string {
  return value.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function toBasicForm(settings: SettingsResponse): BasicForm {
  return {
    download_path: settings.download_path,
    request_base_delay_seconds: settings.request_base_delay_seconds,
    request_random_delay_seconds: settings.request_random_delay_seconds,
    file_download_base_delay_seconds: settings.file_download_base_delay_seconds,
    file_download_random_delay_seconds: settings.file_download_random_delay_seconds,
    max_concurrent_downloads: settings.max_concurrent_downloads,
    max_active_workflow_triggers: settings.max_active_workflow_triggers,
    max_active_run_jobs: settings.max_active_run_jobs,
    min_free_space_gb: settings.min_free_space_gb,
    library_stale_check_days: settings.library_stale_check_days,
    existing_file_behavior: settings.existing_file_behavior
  };
}

export function validateBasic(form: BasicForm, downloadPathEditable: boolean): Record<string, string> {
  const errors: Record<string, string> = {};
  if (downloadPathEditable && !form.download_path.trim()) {
    errors.download_path = "Download path is required.";
  }
  if (form.request_base_delay_seconds < 0) {
    errors.request_base_delay_seconds = "Must be zero or greater.";
  }
  if (form.request_random_delay_seconds < 0) {
    errors.request_random_delay_seconds = "Must be zero or greater.";
  }
  if (form.file_download_base_delay_seconds < 0) {
    errors.file_download_base_delay_seconds = "Must be zero or greater.";
  }
  if (form.file_download_random_delay_seconds < 0) {
    errors.file_download_random_delay_seconds = "Must be zero or greater.";
  }
  if (form.max_concurrent_downloads < 1 || !Number.isInteger(form.max_concurrent_downloads)) {
    errors.max_concurrent_downloads = "Must be a whole number of at least 1.";
  }
  if (form.max_active_workflow_triggers < 1 || !Number.isInteger(form.max_active_workflow_triggers)) {
    errors.max_active_workflow_triggers = "Must be a whole number of at least 1.";
  }
  if (form.max_active_run_jobs < 1 || !Number.isInteger(form.max_active_run_jobs)) {
    errors.max_active_run_jobs = "Must be a whole number of at least 1.";
  }
  if (form.min_free_space_gb < 0) {
    errors.min_free_space_gb = "Must be zero or greater.";
  }
  if (form.library_stale_check_days < 1 || !Number.isInteger(form.library_stale_check_days)) {
    errors.library_stale_check_days = "Must be a whole number of at least 1.";
  }
  return errors;
}

export async function copyCommand(command: string): Promise<void> {
  await navigator.clipboard.writeText(command);
}

export function getPixivPostRedirectReturnTo(value: string): string | null {
  const input = value.trim();
  if (!input) {
    return null;
  }

  try {
    const url = new URL(input);
    if (url.hostname !== "accounts.pixiv.net" || url.pathname !== "/post-redirect") {
      return null;
    }
    return url.searchParams.get("return_to");
  } catch {
    return null;
  }
}

export function isPixivAuthStartUrl(value: string): boolean {
  const input = value.trim();
  if (!input) {
    return false;
  }

  try {
    const url = new URL(input);
    return url.hostname === "app-api.pixiv.net" && url.pathname === "/web/v1/users/auth/pixiv/start";
  } catch {
    return false;
  }
}

export function Field({
  label,
  children,
  error,
  help,
  tooltip
}: {
  label: string;
  children: React.ReactNode;
  error?: string;
  help?: string;
  tooltip?: string;
}): JSX.Element {
  return (
    <label className="block" title={tooltip}>
      <span className="mb-2 block text-sm font-medium">{label}</span>
      {children}
      {help ? <span className="mt-1 block text-xs text-muted-foreground">{help}</span> : null}
      {error ? <span className="mt-1 block text-sm text-destructive">{error}</span> : null}
    </label>
  );
}

export function SettingsSection({
  title,
  description,
  children
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <section className="grid gap-4 py-5 first:pt-0 sm:grid-cols-[180px_1fr]">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

export function SettingsActions({ children }: { children: React.ReactNode }): JSX.Element {
  return <div className="flex flex-wrap gap-2 pt-5">{children}</div>;
}

export function NumberField({
  label,
  value,
  error,
  onChange,
  min = 0,
  max,
  step = 0.1,
  tooltip
}: {
  label: string;
  value: number;
  error?: string;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  tooltip?: string;
}): JSX.Element {
  return (
    <Field label={label} error={error} tooltip={tooltip}>
      <Input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </Field>
  );
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
