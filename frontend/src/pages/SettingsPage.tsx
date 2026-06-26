import * as React from "react";
import {
  DatabaseBackup,
  ExternalLink,
  Eye,
  EyeOff,
  KeyRound,
  RefreshCw,
  Save,
  ShieldCheck,
  Undo2
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getSettings,
  completePixivAuth,
  getPixivBrowserAuthStatus,
  importLegacyDatabase,
  refreshPixivAuth,
  startPixivBrowserAuth,
  startPixivAuth,
  updateSettings,
  validatePixivAuth,
  type PixivBrowserAuthStartResponse,
  type PixivAuthStartResponse,
  type SettingsResponse,
  type SettingsUpdateRequest
} from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { useToast } from "@/components/ToastProvider";

type SettingsForm = SettingsUpdateRequest;

export function SettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const [form, setForm] = React.useState<SettingsForm | null>(null);
  const [showToken, setShowToken] = React.useState(false);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [authFlow, setAuthFlow] = React.useState<PixivAuthStartResponse | null>(null);
  const [browserAuthFlow, setBrowserAuthFlow] = React.useState<PixivBrowserAuthStartResponse | null>(null);
  const [authCode, setAuthCode] = React.useState("");
  const legacyDatabaseInputId = React.useId();
  const pixivReturnToUrl = getPixivPostRedirectReturnTo(authCode);
  const isPixivStartUrl = isPixivAuthStartUrl(authCode);
  const hasIntermediatePixivUrl = Boolean(pixivReturnToUrl || isPixivStartUrl);

  React.useEffect(() => {
    if (settings.data && !form) {
      setForm(toForm(settings.data));
    }
  }, [settings.data, form]);

  React.useEffect(() => {
    if (!browserAuthFlow) {
      return;
    }

    let cancelled = false;
    const poll = async () => {
      try {
        const status = await getPixivBrowserAuthStatus(browserAuthFlow.flow_id);
        if (cancelled) {
          return;
        }
        if (status.status === "completed") {
          pushToast({ title: "Pixiv token saved", description: "Browser sign-in completed.", tone: "success" });
          setBrowserAuthFlow(null);
          void queryClient.invalidateQueries({ queryKey: ["settings"] });
        } else if (status.status === "failed") {
          pushToast({
            title: "Pixiv browser sign-in failed",
            description: status.error ?? "Try again or use manual token entry.",
            tone: "error"
          });
          setBrowserAuthFlow(null);
        }
      } catch (error) {
        if (!cancelled && error instanceof Error) {
          pushToast({ title: "Pixiv browser sign-in failed", description: error.message, tone: "error" });
          setBrowserAuthFlow(null);
        }
      }
    };

    void poll();
    const intervalId = window.setInterval(() => {
      void poll();
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [browserAuthFlow, pushToast, queryClient]);

  const mutation = useMutation({
    mutationFn: (request: SettingsUpdateRequest) => updateSettings(request),
    onSuccess: (response) => {
      pushToast({ title: "Settings saved", tone: "success" });
      setForm(toForm(response));
      setShowToken(false);
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error) => pushToast({ title: "Settings save failed", description: error.message, tone: "error" })
  });
  const authMutation = useMutation({
    mutationFn: validatePixivAuth,
    onSuccess: (response) =>
      pushToast({ title: "Pixiv authentication verified", description: response.message, tone: "success" }),
    onError: (error) =>
      pushToast({ title: "Pixiv authentication failed", description: error.message, tone: "error" })
  });
  const startManualAuthMutation = useMutation({
    mutationFn: startPixivAuth,
    onSuccess: (response) => {
      setAuthFlow(response);
      setAuthCode("");
      window.open(response.login_url, "_blank", "noopener,noreferrer");
      pushToast({ title: "Pixiv sign-in opened", description: "Paste the callback URL or code after logging in." });
    },
    onError: (error) => pushToast({ title: "Could not start Pixiv sign-in", description: error.message, tone: "error" })
  });
  const startBrowserAuthMutation = useMutation({
    mutationFn: startPixivBrowserAuth,
    onSuccess: (response) => {
      setBrowserAuthFlow(response);
      setAuthFlow(null);
      setAuthCode("");
      window.open(response.novnc_url, "_blank", "noopener,noreferrer");
      pushToast({ title: "Pixiv browser sign-in opened", description: "Complete login in the remote browser window." });
    },
    onError: () => {
      startManualAuthMutation.mutate();
    }
  });
  const completeAuthMutation = useMutation({
    mutationFn: completePixivAuth,
    onSuccess: (response) => {
      pushToast({ title: "Pixiv token saved", description: response.message, tone: "success" });
      setForm(toForm(response));
      setAuthFlow(null);
      setAuthCode("");
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error) => pushToast({ title: "Pixiv sign-in failed", description: error.message, tone: "error" })
  });
  const refreshAuthMutation = useMutation({
    mutationFn: refreshPixivAuth,
    onSuccess: (response) => {
      pushToast({ title: "Pixiv token refreshed", description: response.message, tone: "success" });
      setForm(toForm(response));
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error) => pushToast({ title: "Pixiv token refresh failed", description: error.message, tone: "error" })
  });
  const importLegacyDatabaseMutation = useMutation({
    mutationFn: importLegacyDatabase,
    onSuccess: (response) => {
      pushToast({
        title: "Legacy database imported",
        description: `${response.imported_artists} artists imported, ${response.skipped_rows} rows skipped.`,
        tone: "success"
      });
      void queryClient.invalidateQueries({ queryKey: ["artists"] });
    },
    onError: (error) =>
      pushToast({ title: "Legacy database import failed", description: error.message, tone: "error" })
  });

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form) {
      return;
    }
    const nextErrors = validate(form, settings.data.download_path_editable);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }
    mutation.mutate({ ...form, refresh_token: form.refresh_token?.trim() || "" });
  };

  return (
    <>
      <PageHeader title="Settings" description="Configure local download and Pixiv request behavior." />
      <div className="p-4 sm:p-6">
        {settings.isLoading || !form ? (
          <DataState title="Loading settings" variant="loading" />
        ) : settings.isError ? (
          <DataState title="Could not load settings" description={settings.error.message} variant="error" />
        ) : (
          <form className="surface max-w-3xl divide-y p-4" onSubmit={submit}>
            <SettingsSection
              title="Pixiv authentication"
              description="Manage the account token used for Pixiv API requests."
            >
              <div className="space-y-4">
                <Field
                  label="Refresh token"
                  error={errors.refresh_token}
                  tooltip="Pixiv OAuth refresh token. Leave this field blank when saving to keep the existing token."
                  help={
                    settings.data.refresh_token_configured
                      ? `Configured: ${settings.data.refresh_token_preview}`
                      : "No refresh token configured"
                  }
                >
                  <div className="flex gap-2">
                    <Input
                      type={showToken ? "text" : "password"}
                      value={form.refresh_token ?? ""}
                      onChange={(event) => setForm({ ...form, refresh_token: event.target.value })}
                      placeholder="Leave blank to keep existing token"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      aria-label={showToken ? "Hide refresh token" : "Show refresh token"}
                      title={showToken ? "Hide token" : "Show token"}
                      onClick={() => setShowToken((value) => !value)}
                    >
                      {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </Button>
                  </div>
                </Field>

                <div className="rounded-md border bg-muted/20 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      title="Open the Pixiv login flow and save a refresh token after sign-in."
                      disabled={startBrowserAuthMutation.isPending || startManualAuthMutation.isPending}
                      onClick={() => startBrowserAuthMutation.mutate()}
                    >
                      <ExternalLink className="h-4 w-4" aria-hidden="true" />
                      Sign in with Pixiv
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      title="Exchange the saved refresh token for a fresh Pixiv token pair."
                      disabled={refreshAuthMutation.isPending || !settings.data.refresh_token_configured}
                      onClick={() => refreshAuthMutation.mutate()}
                    >
                      <RefreshCw className="h-4 w-4" aria-hidden="true" />
                      Refresh Token
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      title="Verify that the configured Pixiv refresh token can authenticate."
                      disabled={authMutation.isPending}
                      onClick={() => authMutation.mutate()}
                    >
                      <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                      Test Auth
                    </Button>
                  </div>

                  {browserAuthFlow ? (
                    <div className="mt-3 space-y-2 rounded-md border bg-background p-3">
                      <span className="block text-sm font-medium">Waiting for Pixiv browser sign-in</span>
                      <span className="block text-xs text-muted-foreground">
                        Complete Pixiv login in the remote browser window. The token is saved automatically after Pixiv redirects back.
                      </span>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          title="Reopen the remote browser for the current Pixiv sign-in flow."
                          onClick={() => window.open(browserAuthFlow.novnc_url, "_blank", "noopener,noreferrer")}
                        >
                          <ExternalLink className="h-4 w-4" aria-hidden="true" />
                          Open Browser
                        </Button>
                        <Button type="button" variant="outline" onClick={() => setBrowserAuthFlow(null)}>
                          Dismiss
                        </Button>
                      </div>
                    </div>
                  ) : null}

                  {authFlow ? (
                    <div className="mt-3 space-y-2">
                      <textarea
                        className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={authCode}
                        onChange={(event) => setAuthCode(event.target.value)}
                        placeholder="Paste Pixiv callback URL, copied request, cURL, HAR snippet, or authorization code"
                      />
                      {pixivReturnToUrl ? (
                        <Button
                          type="button"
                          variant="outline"
                          title="Open the next Pixiv URL from the pasted intermediate login response."
                          onClick={() => window.open(pixivReturnToUrl, "_blank", "noopener,noreferrer")}
                        >
                          <ExternalLink className="h-4 w-4" aria-hidden="true" />
                          Continue Pixiv Sign-in
                        </Button>
                      ) : null}
                      {isPixivStartUrl ? (
                        <span className="block text-xs text-muted-foreground">
                          This Pixiv URL is an intermediate auth endpoint. Copy the callback request that contains code= from the browser network log.
                        </span>
                      ) : null}
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          title="Exchange the pasted callback URL or authorization code and save the resulting refresh token."
                          disabled={completeAuthMutation.isPending || !authCode.trim() || hasIntermediatePixivUrl}
                          onClick={() =>
                            completeAuthMutation.mutate({
                              flow_id: authFlow.flow_id,
                              code_or_callback_url: authCode.trim()
                            })
                          }
                        >
                          <KeyRound className="h-4 w-4" aria-hidden="true" />
                          Save Pixiv Token
                        </Button>
                        <Button type="button" variant="outline" onClick={() => setAuthFlow(null)}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            </SettingsSection>

            <SettingsSection title="Storage" description="Choose where downloaded artwork files are written.">
              <Field
                label="Download path"
                error={errors.download_path}
                tooltip="Directory where downloaded Pixiv files are stored. Docker runtime fixes this to /app/downloads."
              >
                <Input
                  value={form.download_path}
                  disabled={!settings.data.download_path_editable}
                  onChange={(event) => setForm({ ...form, download_path: event.target.value })}
                />
              </Field>
            </SettingsSection>

            <SettingsSection title="Download behavior" description="Control how the downloader handles files that already exist.">
              <div className="grid gap-3 rounded-md border bg-muted/30 p-3 sm:grid-cols-2">
                <label
                  className="flex items-center gap-2 text-sm"
                  title="When a target file already exists, leave it untouched and mark that file as skipped."
                >
                  <input
                    type="checkbox"
                    checked={form.skip_existing_files}
                    onChange={(event) => setForm({ ...form, skip_existing_files: event.target.checked })}
                  />
                  Skip existing files
                </label>
                <label
                  className="flex items-center gap-2 text-sm"
                  title="Allow downloads to replace files that already exist at the target path."
                >
                  <input
                    type="checkbox"
                    checked={form.overwrite_existing_files}
                    onChange={(event) => setForm({ ...form, overwrite_existing_files: event.target.checked })}
                  />
                  Overwrite existing files
                </label>
              </div>
            </SettingsSection>

            <SettingsSection title="Requests and performance" description="Tune Pixiv request pacing and download concurrency.">
              <div className="grid gap-4 sm:grid-cols-3">
                <NumberField
                  label="Base delay seconds"
                  value={form.request_base_delay_seconds}
                  error={errors.request_base_delay_seconds}
                  tooltip="Fixed minimum wait before each Pixiv request or download attempt."
                  onChange={(value) => setForm({ ...form, request_base_delay_seconds: value })}
                />
                <NumberField
                  label="Random delay seconds"
                  value={form.request_random_delay_seconds}
                  error={errors.request_random_delay_seconds}
                  tooltip="Extra random wait from 0 up to this many seconds, added on top of the base delay."
                  onChange={(value) => setForm({ ...form, request_random_delay_seconds: value })}
                />
                <NumberField
                  label="Max concurrent"
                  value={form.max_concurrent_downloads}
                  error={errors.max_concurrent_downloads}
                  min={1}
                  step={1}
                  tooltip="Maximum number of downloads allowed to run at the same time. Minimum is 1."
                  onChange={(value) => setForm({ ...form, max_concurrent_downloads: Math.max(1, value) })}
                />
              </div>
            </SettingsSection>

            <SettingsSection title="Data maintenance" description="Run one-off maintenance tasks for local library data.">
              <div className="rounded-md border bg-muted/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    id={legacyDatabaseInputId}
                    className="hidden"
                    type="file"
                    accept=".db,.sqlite,.sqlite3,application/vnd.sqlite3,application/octet-stream"
                    disabled={importLegacyDatabaseMutation.isPending}
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      event.target.value = "";
                      if (file) {
                        importLegacyDatabaseMutation.mutate(file);
                      }
                    }}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    title="Import artists and artwork metadata from an archived PyQt pixiv.db or SQLite database."
                    disabled={importLegacyDatabaseMutation.isPending}
                    onClick={() => document.getElementById(legacyDatabaseInputId)?.click()}
                  >
                    <DatabaseBackup className="h-4 w-4" aria-hidden="true" />
                    Import Legacy Database
                  </Button>
                  {importLegacyDatabaseMutation.data ? (
                    <span className="text-xs text-muted-foreground">
                      {importLegacyDatabaseMutation.data.imported_artists} of{" "}
                      {importLegacyDatabaseMutation.data.total_rows} rows imported.
                    </span>
                  ) : null}
                </div>
              </div>
            </SettingsSection>

            <div className="flex flex-wrap gap-2 pt-5">
              <Button type="submit" title="Save the current settings to config/settings.json." disabled={mutation.isPending}>
                <Save className="h-4 w-4" aria-hidden="true" />
                Save
              </Button>
              <Button
                type="button"
                variant="outline"
                title="Restore the form values from the last loaded settings response."
                onClick={() => setForm(toForm(settings.data))}
              >
                <Undo2 className="h-4 w-4" aria-hidden="true" />
                Reset
              </Button>
            </div>
          </form>
        )}
      </div>
    </>
  );
}

function toForm(settings: SettingsResponse): SettingsForm {
  return {
    download_path: settings.download_path,
    refresh_token: "",
    request_base_delay_seconds: settings.request_base_delay_seconds,
    request_random_delay_seconds: settings.request_random_delay_seconds,
    max_concurrent_downloads: settings.max_concurrent_downloads,
    overwrite_existing_files: settings.overwrite_existing_files,
    skip_existing_files: settings.skip_existing_files
  };
}

function validate(form: SettingsForm, downloadPathEditable: boolean): Record<string, string> {
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
  if (form.max_concurrent_downloads < 1 || !Number.isInteger(form.max_concurrent_downloads)) {
    errors.max_concurrent_downloads = "Must be a whole number of at least 1.";
  }
  return errors;
}

function getPixivPostRedirectReturnTo(value: string): string | null {
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

function isPixivAuthStartUrl(value: string): boolean {
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

function Field({
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

function SettingsSection({
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

function NumberField({
  label,
  value,
  error,
  onChange,
  min = 0,
  step = 0.1,
  tooltip
}: {
  label: string;
  value: number;
  error?: string;
  onChange: (value: number) => void;
  min?: number;
  step?: number;
  tooltip?: string;
}): JSX.Element {
  return (
    <Field label={label} error={error} tooltip={tooltip}>
      <Input
        type="number"
        min={min}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </Field>
  );
}
