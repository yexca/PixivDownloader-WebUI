import * as React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  DatabaseBackup,
  ExternalLink,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  RefreshCw,
  Save,
  ShieldCheck,
  Undo2
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getSettings,
  completePixivAuth,
  getPixivBrowserAuthServiceStatus,
  getPixivBrowserAuthStatus,
  importLegacyDatabase,
  refreshPixivAuth,
  startPixivBrowserAuth,
  startPixivAuth,
  updateSettings,
  validatePixivAuth,
  type PixivBrowserAuthStartResponse,
  type PixivBrowserAuthServiceStatusResponse,
  type PixivAuthStartResponse,
  type SettingsResponse,
  type SettingsUpdateRequest
} from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs } from "@/components/ui/tabs";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { useToast } from "@/components/ToastProvider";

type SettingsTab = "basic" | "pixiv" | "advanced";
type BasicForm = Pick<
  SettingsUpdateRequest,
  | "download_path"
  | "request_base_delay_seconds"
  | "request_random_delay_seconds"
  | "max_concurrent_downloads"
  | "max_active_scheduled_tasks"
  | "max_active_one_time_tasks"
  | "min_free_space_gb"
  | "library_stale_check_days"
  | "overwrite_existing_files"
  | "skip_existing_files"
>;
type TokenStatusState = "unconfigured" | "checking" | "valid" | "invalid";

type TokenStatus = {
  state: TokenStatusState;
  message: string;
};

class AuthBrowserUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthBrowserUnavailableError";
  }
}

class AuthBrowserNotConfiguredError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthBrowserNotConfiguredError";
  }
}

export function SettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const [activeTab, setActiveTab] = React.useState<SettingsTab>("basic");
  const [basicForm, setBasicForm] = React.useState<BasicForm | null>(null);
  const [refreshToken, setRefreshToken] = React.useState("");
  const [showToken, setShowToken] = React.useState(false);
  const [basicErrors, setBasicErrors] = React.useState<Record<string, string>>({});
  const [authFlow, setAuthFlow] = React.useState<PixivAuthStartResponse | null>(null);
  const [browserAuthFlow, setBrowserAuthFlow] = React.useState<PixivBrowserAuthStartResponse | null>(null);
  const [authBrowserDialog, setAuthBrowserDialog] = React.useState<AuthBrowserDialog | null>(null);
  const [authCode, setAuthCode] = React.useState("");
  const [tokenStatus, setTokenStatus] = React.useState<TokenStatus>({
    state: "checking",
    message: "Checking Pixiv token status."
  });
  const legacyDatabaseInputId = React.useId();
  const pixivReturnToUrl = getPixivPostRedirectReturnTo(authCode);
  const isPixivStartUrl = isPixivAuthStartUrl(authCode);
  const hasIntermediatePixivUrl = Boolean(pixivReturnToUrl || isPixivStartUrl);

  React.useEffect(() => {
    if (settings.data && !basicForm) {
      setBasicForm(toBasicForm(settings.data));
    }
  }, [basicForm, settings.data]);

  const remindToStopAuthBrowserIfRunning = React.useCallback(async () => {
    try {
      const status = await getPixivBrowserAuthServiceStatus();
      if (status.running) {
        setAuthBrowserDialog({ type: "stop", status });
      }
    } catch {
      // If status probing fails after auth, do not interrupt the completed token flow.
    }
  }, []);

  const runPixivTokenCheck = React.useCallback(
    async ({ notify = false, force = false }: { notify?: boolean; force?: boolean } = {}) => {
      if (!force && !settings.data?.refresh_token_configured) {
        setTokenStatus({ state: "unconfigured", message: "No Pixiv refresh token is configured." });
        return;
      }
      setTokenStatus({ state: "checking", message: "Checking Pixiv authentication." });
      try {
        const response = await validatePixivAuth();
        setTokenStatus({ state: "valid", message: response.message });
        if (notify) {
          pushToast({ title: "Pixiv authentication verified", description: response.message, tone: "success" });
        }
        void remindToStopAuthBrowserIfRunning();
      } catch (error) {
        const message = error instanceof Error ? error.message : "Pixiv authentication could not be verified.";
        setTokenStatus({ state: "invalid", message });
        if (notify) {
          pushToast({ title: "Pixiv authentication failed", description: message, tone: "error" });
        }
      }
    },
    [pushToast, remindToStopAuthBrowserIfRunning, settings.data?.refresh_token_configured]
  );

  React.useEffect(() => {
    if (activeTab === "pixiv") {
      void runPixivTokenCheck();
    }
  }, [activeTab, runPixivTokenCheck]);

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
          void runPixivTokenCheck();
          void remindToStopAuthBrowserIfRunning();
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
  }, [browserAuthFlow, pushToast, queryClient, remindToStopAuthBrowserIfRunning, runPixivTokenCheck]);

  const basicMutation = useMutation({
    mutationFn: (request: BasicForm) => updateSettings(request),
    onSuccess: (response) => {
      pushToast({ title: "Basic settings saved", tone: "success" });
      setBasicForm(toBasicForm(response));
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error) => pushToast({ title: "Basic settings save failed", description: error.message, tone: "error" })
  });

  const saveTokenMutation = useMutation({
    mutationFn: (token: string) => updateSettings({ refresh_token: token }),
    onSuccess: () => {
      pushToast({ title: "Pixiv token saved", tone: "success" });
      setRefreshToken("");
      setShowToken(false);
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
      void runPixivTokenCheck({ force: true });
    },
    onError: (error) => pushToast({ title: "Pixiv token save failed", description: error.message, tone: "error" })
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
    mutationFn: async () => {
      const status = await getPixivBrowserAuthServiceStatus();
      if (!status.configured) {
        throw new AuthBrowserNotConfiguredError(status.message);
      }
      if (!status.running) {
        setAuthBrowserDialog({ type: "start", status });
        throw new AuthBrowserUnavailableError(status.message);
      }
      return startPixivBrowserAuth();
    },
    onSuccess: (response) => {
      setBrowserAuthFlow(response);
      setAuthFlow(null);
      setAuthCode("");
      window.open(response.novnc_url, "_blank", "noopener,noreferrer");
      pushToast({ title: "Pixiv browser sign-in opened", description: "Complete login in the remote browser window." });
    },
    onError: (error) => {
      if (error instanceof AuthBrowserNotConfiguredError) {
        startManualAuthMutation.mutate();
      } else if (!(error instanceof AuthBrowserUnavailableError)) {
        pushToast({ title: "Pixiv browser sign-in failed", description: error.message, tone: "error" });
      }
    }
  });

  const completeAuthMutation = useMutation({
    mutationFn: completePixivAuth,
    onSuccess: (response) => {
      pushToast({ title: "Pixiv token saved", description: response.message, tone: "success" });
      setAuthFlow(null);
      setAuthCode("");
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
      void runPixivTokenCheck({ force: true });
      void remindToStopAuthBrowserIfRunning();
    },
    onError: (error) => pushToast({ title: "Pixiv sign-in failed", description: error.message, tone: "error" })
  });

  const refreshAuthMutation = useMutation({
    mutationFn: refreshPixivAuth,
    onSuccess: (response) => {
      pushToast({ title: "Pixiv token refreshed", description: response.message, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
      void runPixivTokenCheck({ force: true });
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

  const submitBasic = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!basicForm || !settings.data) {
      return;
    }
    const nextErrors = validateBasic(basicForm, settings.data.download_path_editable);
    setBasicErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }
    basicMutation.mutate(basicForm);
  };

  const saveManualToken = () => {
    const token = refreshToken.trim();
    if (!token) {
      pushToast({ title: "Pixiv token is empty", description: "Paste a refresh token before saving.", tone: "error" });
      return;
    }
    saveTokenMutation.mutate(token);
  };

  return (
    <>
      <PageHeader title="Settings" description="Configure local download and Pixiv request behavior." />
      <div className="p-4 sm:p-6">
        {settings.isLoading || !basicForm ? (
          <DataState title="Loading settings" variant="loading" />
        ) : settings.isError ? (
          <DataState title="Could not load settings" description={settings.error.message} variant="error" />
        ) : (
          <div className="surface max-w-4xl p-4">
            <Tabs
              value={activeTab}
              onValueChange={setActiveTab}
              items={[
                { value: "basic", label: "Basic" },
                { value: "pixiv", label: "Pixiv" },
                { value: "advanced", label: "Advanced" }
              ]}
            />

            {activeTab === "basic" ? (
              <BasicSettingsTab
                form={basicForm}
                settings={settings.data}
                errors={basicErrors}
                isSaving={basicMutation.isPending}
                onSubmit={submitBasic}
                onChange={setBasicForm}
                onReset={() => {
                  setBasicErrors({});
                  setBasicForm(toBasicForm(settings.data));
                }}
              />
            ) : null}

            {activeTab === "pixiv" ? (
              <PixivSettingsTab
                authCode={authCode}
                authFlow={authFlow}
                browserAuthFlow={browserAuthFlow}
                completeAuthPending={completeAuthMutation.isPending}
                hasIntermediatePixivUrl={hasIntermediatePixivUrl}
                isPixivStartUrl={isPixivStartUrl}
                pixivReturnToUrl={pixivReturnToUrl}
                refreshAuthPending={refreshAuthMutation.isPending}
                refreshToken={refreshToken}
                saveTokenPending={saveTokenMutation.isPending}
                settings={settings.data}
                showToken={showToken}
                startBrowserAuthPending={startBrowserAuthMutation.isPending}
                startManualAuthPending={startManualAuthMutation.isPending}
                tokenStatus={tokenStatus}
                onAuthCodeChange={setAuthCode}
                onCancelAuthFlow={() => setAuthFlow(null)}
                onCompleteAuth={() =>
                  authFlow
                    ? completeAuthMutation.mutate({
                        flow_id: authFlow.flow_id,
                        code_or_callback_url: authCode.trim()
                      })
                    : undefined
                }
                onDismissBrowserFlow={() => setBrowserAuthFlow(null)}
                onOpenBrowserFlow={() =>
                  browserAuthFlow ? window.open(browserAuthFlow.novnc_url, "_blank", "noopener,noreferrer") : undefined
                }
                onOpenContinueUrl={() =>
                  pixivReturnToUrl ? window.open(pixivReturnToUrl, "_blank", "noopener,noreferrer") : undefined
                }
                onRefreshAuth={() => refreshAuthMutation.mutate()}
                onRefreshTokenChange={setRefreshToken}
                onRunTokenCheck={() => void runPixivTokenCheck({ notify: true })}
                onSaveManualToken={saveManualToken}
                onStartBrowserAuth={() => startBrowserAuthMutation.mutate()}
                onToggleToken={() => setShowToken((value) => !value)}
              />
            ) : null}

            {activeTab === "advanced" ? (
              <AdvancedSettingsTab
                importLegacyDatabaseData={importLegacyDatabaseMutation.data}
                isImporting={importLegacyDatabaseMutation.isPending}
                legacyDatabaseInputId={legacyDatabaseInputId}
                onImportLegacyDatabase={(file) => importLegacyDatabaseMutation.mutate(file)}
              />
            ) : null}
          </div>
        )}
      </div>
      <AuthBrowserCommandDialog
        dialog={authBrowserDialog}
        onClose={() => setAuthBrowserDialog(null)}
        onCopy={(command) => {
          void copyCommand(command)
            .then(() => pushToast({ title: "Command copied", tone: "success" }))
            .catch((error: Error) =>
              pushToast({ title: "Command copy failed", description: error.message, tone: "error" })
            );
        }}
        onUseManual={() => {
          setAuthBrowserDialog(null);
          startManualAuthMutation.mutate();
        }}
      />
    </>
  );
}

function BasicSettingsTab({
  form,
  settings,
  errors,
  isSaving,
  onSubmit,
  onChange,
  onReset
}: {
  form: BasicForm;
  settings: SettingsResponse;
  errors: Record<string, string>;
  isSaving: boolean;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onChange: (form: BasicForm) => void;
  onReset: () => void;
}): JSX.Element {
  return (
    <form className="mt-5 divide-y" onSubmit={onSubmit}>
      <SettingsSection title="Storage" description="Choose where downloaded artwork files are written.">
        <Field
          label="Download path"
          error={errors.download_path}
          tooltip="Directory where downloaded Pixiv files are stored. Docker runtime fixes this to /app/downloads."
        >
          <Input
            value={form.download_path}
            disabled={!settings.download_path_editable}
            onChange={(event) => onChange({ ...form, download_path: event.target.value })}
          />
        </Field>
      </SettingsSection>

      <SettingsSection title="Download behavior" description="Control download concurrency and existing file handling.">
        <div className="space-y-4">
          <div className="grid gap-3 rounded-md border bg-muted/30 p-3 sm:grid-cols-2">
            <label
              className="flex items-center gap-2 text-sm"
              title="When a target file already exists, leave it untouched and mark that file as skipped."
            >
              <input
                type="checkbox"
                checked={form.skip_existing_files}
                onChange={(event) => onChange({ ...form, skip_existing_files: event.target.checked })}
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
                onChange={(event) => onChange({ ...form, overwrite_existing_files: event.target.checked })}
              />
              Overwrite existing files
            </label>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title="Requests and performance" description="Tune Pixiv request pacing and download concurrency.">
        <div className="space-y-3">
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField
              label="Base delay seconds"
              value={form.request_base_delay_seconds}
              error={errors.request_base_delay_seconds}
              tooltip="Fixed minimum wait before each Pixiv request or download attempt."
              onChange={(value) => onChange({ ...form, request_base_delay_seconds: value })}
            />
            <NumberField
              label="Random delay seconds"
              value={form.request_random_delay_seconds}
              error={errors.request_random_delay_seconds}
              tooltip="Extra random wait from 0 up to this many seconds, added on top of the base delay."
              onChange={(value) => onChange({ ...form, request_random_delay_seconds: value })}
            />
          </div>
          <p className="text-xs leading-5 text-muted-foreground">
            Each request waits base delay + random(0, random delay) seconds before running.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField
              label="Max concurrent"
              value={form.max_concurrent_downloads}
              error={errors.max_concurrent_downloads}
              min={1}
              step={1}
              tooltip="Maximum number of downloads allowed to run at the same time. Minimum is 1."
              onChange={(value) => onChange({ ...form, max_concurrent_downloads: Math.max(1, value) })}
            />
            <NumberField
              label="Max active schedules"
              value={form.max_active_scheduled_tasks}
              error={errors.max_active_scheduled_tasks}
              min={1}
              step={1}
              tooltip="Maximum number of schedules allowed to stay active. Extra enabled schedules wait as inactive."
              onChange={(value) => onChange({ ...form, max_active_scheduled_tasks: Math.max(1, Math.trunc(value)) })}
            />
            <NumberField
              label="Max active one-time tasks"
              value={form.max_active_one_time_tasks}
              error={errors.max_active_one_time_tasks}
              min={1}
              step={1}
              tooltip="Maximum number of one-time workflow jobs allowed to wait or run. Extra one-time jobs stay inactive."
              onChange={(value) => onChange({ ...form, max_active_one_time_tasks: Math.max(1, Math.trunc(value)) })}
            />
            <NumberField
              label="Minimum free GB"
              value={form.min_free_space_gb}
              error={errors.min_free_space_gb}
              min={0}
              step={0.5}
              tooltip="Download jobs are not created when the download disk has less free space than this value."
              onChange={(value) => onChange({ ...form, min_free_space_gb: Math.max(0, value) })}
            />
            <NumberField
              label="Library stale days"
              value={form.library_stale_check_days}
              error={errors.library_stale_check_days}
              min={1}
              step={1}
              tooltip="Artists checked before this many days ago are shown as check due in Library."
              onChange={(value) => onChange({ ...form, library_stale_check_days: Math.max(1, Math.trunc(value)) })}
            />
          </div>
        </div>
      </SettingsSection>

      <SettingsActions>
        <Button type="submit" title="Save basic settings to config/settings.json." disabled={isSaving}>
          <Save className="h-4 w-4" aria-hidden="true" />
          Save Basic
        </Button>
        <Button type="button" variant="outline" title="Restore basic settings from the last loaded values." onClick={onReset}>
          <Undo2 className="h-4 w-4" aria-hidden="true" />
          Reset
        </Button>
      </SettingsActions>
    </form>
  );
}

function PixivSettingsTab({
  authCode,
  authFlow,
  browserAuthFlow,
  completeAuthPending,
  hasIntermediatePixivUrl,
  isPixivStartUrl,
  pixivReturnToUrl,
  refreshAuthPending,
  refreshToken,
  saveTokenPending,
  settings,
  showToken,
  startBrowserAuthPending,
  startManualAuthPending,
  tokenStatus,
  onAuthCodeChange,
  onCancelAuthFlow,
  onCompleteAuth,
  onDismissBrowserFlow,
  onOpenBrowserFlow,
  onOpenContinueUrl,
  onRefreshAuth,
  onRefreshTokenChange,
  onRunTokenCheck,
  onSaveManualToken,
  onStartBrowserAuth,
  onToggleToken
}: {
  authCode: string;
  authFlow: PixivAuthStartResponse | null;
  browserAuthFlow: PixivBrowserAuthStartResponse | null;
  completeAuthPending: boolean;
  hasIntermediatePixivUrl: boolean;
  isPixivStartUrl: boolean;
  pixivReturnToUrl: string | null;
  refreshAuthPending: boolean;
  refreshToken: string;
  saveTokenPending: boolean;
  settings: SettingsResponse;
  showToken: boolean;
  startBrowserAuthPending: boolean;
  startManualAuthPending: boolean;
  tokenStatus: TokenStatus;
  onAuthCodeChange: (value: string) => void;
  onCancelAuthFlow: () => void;
  onCompleteAuth: () => void;
  onDismissBrowserFlow: () => void;
  onOpenBrowserFlow: () => void;
  onOpenContinueUrl: () => void;
  onRefreshAuth: () => void;
  onRefreshTokenChange: (value: string) => void;
  onRunTokenCheck: () => void;
  onSaveManualToken: () => void;
  onStartBrowserAuth: () => void;
  onToggleToken: () => void;
}): JSX.Element {
  return (
    <div className="mt-5 divide-y">
      <SettingsSection title="Token status" description="Validate the Pixiv account token used for API requests.">
        <PixivTokenStatus status={tokenStatus} preview={settings.refresh_token_preview} />
      </SettingsSection>

      <SettingsSection title="Pixiv authentication" description="Sign in, refresh, test, or replace the saved token.">
        <div className="space-y-4">
          <Field
            label="New refresh token"
            tooltip="Paste a new Pixiv OAuth refresh token. Saved tokens are masked in normal settings responses."
            help={
              settings.refresh_token_configured
                ? `Saved token: ${settings.refresh_token_preview}`
                : "No saved token"
            }
          >
            <div className="flex gap-2">
              <Input
                type={showToken ? "text" : "password"}
                value={refreshToken}
                onChange={(event) => onRefreshTokenChange(event.target.value)}
                placeholder="Paste a new refresh token"
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label={showToken ? "Hide refresh token" : "Show refresh token"}
                title={showToken ? "Hide token" : "Show token"}
                onClick={onToggleToken}
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
                title="Save the pasted refresh token."
                disabled={saveTokenPending || !refreshToken.trim()}
                onClick={onSaveManualToken}
              >
                <KeyRound className="h-4 w-4" aria-hidden="true" />
                Save Token
              </Button>
              <Button
                type="button"
                variant="outline"
                title="Open the Pixiv login flow and save a refresh token after sign-in."
                disabled={startBrowserAuthPending || startManualAuthPending}
                onClick={onStartBrowserAuth}
              >
                <ExternalLink className="h-4 w-4" aria-hidden="true" />
                Sign in with Pixiv
              </Button>
              <Button
                type="button"
                variant="outline"
                title="Exchange the saved refresh token for a fresh Pixiv token pair."
                disabled={refreshAuthPending || !settings.refresh_token_configured}
                onClick={onRefreshAuth}
              >
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                Refresh Token
              </Button>
              <Button
                type="button"
                variant="outline"
                title="Verify that the configured Pixiv refresh token can authenticate."
                disabled={tokenStatus.state === "checking"}
                onClick={onRunTokenCheck}
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
                    onClick={onOpenBrowserFlow}
                  >
                    <ExternalLink className="h-4 w-4" aria-hidden="true" />
                    Open Browser
                  </Button>
                  <Button type="button" variant="outline" onClick={onDismissBrowserFlow}>
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
                  onChange={(event) => onAuthCodeChange(event.target.value)}
                  placeholder="Paste Pixiv callback URL, copied request, cURL, HAR snippet, or authorization code"
                />
                {pixivReturnToUrl ? (
                  <Button
                    type="button"
                    variant="outline"
                    title="Open the next Pixiv URL from the pasted intermediate login response."
                    onClick={onOpenContinueUrl}
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
                    disabled={completeAuthPending || !authCode.trim() || hasIntermediatePixivUrl}
                    onClick={onCompleteAuth}
                  >
                    <KeyRound className="h-4 w-4" aria-hidden="true" />
                    Save Pixiv Token
                  </Button>
                  <Button type="button" variant="outline" onClick={onCancelAuthFlow}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}

function AdvancedSettingsTab({
  importLegacyDatabaseData,
  isImporting,
  legacyDatabaseInputId,
  onImportLegacyDatabase
}: {
  importLegacyDatabaseData?: { imported_artists: number; total_rows: number };
  isImporting: boolean;
  legacyDatabaseInputId: string;
  onImportLegacyDatabase: (file: File) => void;
}): JSX.Element {
  return (
    <div className="mt-5 divide-y">
      <SettingsSection title="Data maintenance" description="Run one-off maintenance tasks for local library data.">
        <div className="rounded-md border bg-muted/20 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <input
              id={legacyDatabaseInputId}
              className="hidden"
              type="file"
              accept=".db,.sqlite,.sqlite3,application/vnd.sqlite3,application/octet-stream"
              disabled={isImporting}
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) {
                  onImportLegacyDatabase(file);
                }
              }}
            />
            <Button
              type="button"
              variant="outline"
              title="Import artists and artwork metadata from an old PyQt pixiv.db or SQLite database."
              disabled={isImporting}
              onClick={() => document.getElementById(legacyDatabaseInputId)?.click()}
            >
              <DatabaseBackup className="h-4 w-4" aria-hidden="true" />
              Import Legacy Database
            </Button>
            {importLegacyDatabaseData ? (
              <span className="text-xs text-muted-foreground">
                {importLegacyDatabaseData.imported_artists} of {importLegacyDatabaseData.total_rows} rows imported.
              </span>
            ) : null}
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}

type AuthBrowserDialog = {
  type: "start" | "stop";
  status: PixivBrowserAuthServiceStatusResponse;
};

function AuthBrowserCommandDialog({
  dialog,
  onClose,
  onCopy,
  onUseManual
}: {
  dialog: AuthBrowserDialog | null;
  onClose: () => void;
  onCopy: (command: string) => void;
  onUseManual: () => void;
}): JSX.Element | null {
  if (!dialog) {
    return null;
  }

  const command = dialog.type === "start" ? dialog.status.start_command : dialog.status.stop_command;
  const title = dialog.type === "start" ? "Start Pixiv auth browser" : "Pixiv auth browser can be stopped";
  const description =
    dialog.type === "start"
      ? "The browser authentication service is not running. Start it, then click Sign in with Pixiv again."
      : "Pixiv authentication is configured. The browser service is only needed when signing in again.";

  return (
    <Dialog
      open
      title={title}
      description={description}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
      footer={
        <>
          {dialog.type === "start" ? (
            <Button type="button" variant="outline" onClick={onUseManual}>
              Use manual sign-in
            </Button>
          ) : null}
          <Button type="button" onClick={onClose}>
            Done
          </Button>
        </>
      }
    >
      <CommandBlock command={command} onCopy={() => onCopy(command)} />
    </Dialog>
  );
}

function CommandBlock({ command, onCopy }: { command: string; onCopy: () => void }): JSX.Element {
  return (
    <div className="flex items-center gap-2 rounded-md border bg-muted/40 p-2">
      <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap text-sm">{command}</code>
      <Button type="button" variant="outline" size="icon" title="Copy command" aria-label="Copy command" onClick={onCopy}>
        <Copy className="h-4 w-4" aria-hidden="true" />
      </Button>
    </div>
  );
}

function PixivTokenStatus({ status, preview }: { status: TokenStatus; preview: string }): JSX.Element {
  const Icon = status.state === "checking" ? Loader2 : status.state === "valid" ? CheckCircle2 : AlertTriangle;
  const label =
    status.state === "valid"
      ? "Token verified"
      : status.state === "checking"
        ? "Checking token"
        : status.state === "invalid"
          ? "Token needs attention"
          : "Token not configured";
  const className =
    status.state === "valid"
      ? "border-green-200 bg-green-50 text-green-900"
      : status.state === "checking"
        ? "border-border bg-muted/30 text-foreground"
        : "border-yellow-200 bg-yellow-50 text-yellow-950";

  return (
    <div className={`rounded-md border p-3 ${className}`}>
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${status.state === "checking" ? "animate-spin" : ""}`} aria-hidden="true" />
        <div className="min-w-0">
          <span className="block text-sm font-semibold">{label}</span>
          <span className="mt-1 block text-sm leading-5">{status.message}</span>
          {preview ? <span className="mt-1 block text-xs opacity-75">Saved token: {preview}</span> : null}
        </div>
      </div>
    </div>
  );
}

function toBasicForm(settings: SettingsResponse): BasicForm {
  return {
    download_path: settings.download_path,
    request_base_delay_seconds: settings.request_base_delay_seconds,
    request_random_delay_seconds: settings.request_random_delay_seconds,
    max_concurrent_downloads: settings.max_concurrent_downloads,
    max_active_scheduled_tasks: settings.max_active_scheduled_tasks,
    max_active_one_time_tasks: settings.max_active_one_time_tasks,
    min_free_space_gb: settings.min_free_space_gb,
    library_stale_check_days: settings.library_stale_check_days,
    overwrite_existing_files: settings.overwrite_existing_files,
    skip_existing_files: settings.skip_existing_files
  };
}

function validateBasic(form: BasicForm, downloadPathEditable: boolean): Record<string, string> {
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
  if (form.max_active_scheduled_tasks < 1 || !Number.isInteger(form.max_active_scheduled_tasks)) {
    errors.max_active_scheduled_tasks = "Must be a whole number of at least 1.";
  }
  if (form.max_active_one_time_tasks < 1 || !Number.isInteger(form.max_active_one_time_tasks)) {
    errors.max_active_one_time_tasks = "Must be a whole number of at least 1.";
  }
  if (form.min_free_space_gb < 0) {
    errors.min_free_space_gb = "Must be zero or greater.";
  }
  if (form.library_stale_check_days < 1 || !Number.isInteger(form.library_stale_check_days)) {
    errors.library_stale_check_days = "Must be a whole number of at least 1.";
  }
  return errors;
}

async function copyCommand(command: string): Promise<void> {
  await navigator.clipboard.writeText(command);
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

function SettingsActions({ children }: { children: React.ReactNode }): JSX.Element {
  return <div className="flex flex-wrap gap-2 pt-5">{children}</div>;
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
