import * as React from "react";
import { Copy, DatabaseBackup } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  completePixivAuth,
  getPixivBrowserAuthServiceStatus,
  getPixivBrowserAuthStatus,
  getSettings,
  importLegacyDatabase,
  refreshPixivAuth,
  startPixivAuth,
  startPixivBrowserAuth,
  testPixivConnection,
  updateSettings,
  validatePixivAuth,
  type PixivAuthStartResponse,
  type PixivBrowserAuthStartResponse
} from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Tabs } from "@/components/ui/tabs";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { useToast } from "@/components/ToastProvider";
import { useUiStore } from "@/hooks/useUiStore";
import { BasicSettingsTab } from "@/pages/settings/BasicSettingsTab";
import {
  copyCommand,
  getPixivPostRedirectReturnTo,
  isPixivAuthStartUrl,
  notConfiguredAuthStatus,
  notConfiguredConnectionStatus,
  resetTestStatuses,
  toBasicForm,
  validateBasic,
  type AuthBrowserDialog,
  type BasicForm,
  type SettingsTab,
  type TestStatus
} from "@/pages/settings/shared";

const PixivSettingsTab = React.lazy(() =>
  import("@/pages/settings/PixivSettingsTab").then((module) => ({ default: module.PixivSettingsTab }))
);
const AppearanceSettingsTab = React.lazy(() =>
  import("@/pages/settings/AppearanceSettingsTab").then((module) => ({ default: module.AppearanceSettingsTab }))
);
const AdvancedSettingsTab = React.lazy(() =>
  import("@/pages/settings/AdvancedSettingsTab").then((module) => ({ default: module.AdvancedSettingsTab }))
);

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
  const [legacyImportDialogOpen, setLegacyImportDialogOpen] = React.useState(false);
  const [authCode, setAuthCode] = React.useState("");
  const [authTestStatus, setAuthTestStatus] = React.useState<TestStatus>(notConfiguredAuthStatus());
  const [connectionTestStatus, setConnectionTestStatus] = React.useState<TestStatus>(notConfiguredConnectionStatus());
  const appearanceSettings = useUiStore((state) => state.appearanceSettings);
  const customThemePresets = useUiStore((state) => state.customThemePresets);
  const activeThemePreset = useUiStore((state) => state.activeThemePreset);
  const setFollowSystemTheme = useUiStore((state) => state.setFollowSystemTheme);
  const setActiveThemePreset = useUiStore((state) => state.setActiveThemePreset);
  const setSystemThemePreset = useUiStore((state) => state.setSystemThemePreset);
  const createThemePreset = useUiStore((state) => state.createThemePreset);
  const updateThemePreset = useUiStore((state) => state.updateThemePreset);
  const deleteThemePreset = useUiStore((state) => state.deleteThemePreset);
  const legacyDatabaseInputId = React.useId();
  const pixivReturnToUrl = getPixivPostRedirectReturnTo(authCode);
  const isPixivStartUrl = isPixivAuthStartUrl(authCode);
  const hasIntermediatePixivUrl = Boolean(pixivReturnToUrl || isPixivStartUrl);
  const settingsLoaded = Boolean(settings.data);
  const refreshTokenConfigured = settings.data?.refresh_token_configured ?? false;

  React.useEffect(() => {
    if (settings.data && !basicForm) {
      setBasicForm(toBasicForm(settings.data));
    }
  }, [basicForm, settings.data]);

  React.useEffect(() => {
    if (!settingsLoaded) {
      return;
    }
    resetTestStatuses(refreshTokenConfigured, setAuthTestStatus, setConnectionTestStatus);
  }, [settingsLoaded, refreshTokenConfigured]);

  const resetCurrentTokenTests = React.useCallback(() => {
    resetTestStatuses(true, setAuthTestStatus, setConnectionTestStatus);
  }, []);

  const resetMissingTokenTests = React.useCallback(() => {
    resetTestStatuses(false, setAuthTestStatus, setConnectionTestStatus);
  }, []);

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

  const refreshSettings = React.useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["settings"] });
  }, [queryClient]);

  const runAuthTest = React.useCallback(
    async ({ notify = false }: { notify?: boolean } = {}) => {
      if (!refreshTokenConfigured) {
        resetMissingTokenTests();
        return;
      }
      setAuthTestStatus({ state: "checking", message: "Testing Pixiv authentication." });
      try {
        const response = await validatePixivAuth();
        setAuthTestStatus({ state: "valid", message: response.message, checkedAt: new Date() });
        if (notify) {
          pushToast({ title: "Pixiv authentication verified", description: response.message, tone: "success" });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Pixiv authentication could not be verified.";
        setAuthTestStatus({ state: "invalid", message, checkedAt: new Date() });
        if (notify) {
          pushToast({ title: "Pixiv authentication failed", description: message, tone: "error" });
        }
      }
    },
    [pushToast, refreshTokenConfigured, resetMissingTokenTests]
  );

  const runConnectionTest = React.useCallback(
    async ({ notify = false }: { notify?: boolean } = {}) => {
      if (!refreshTokenConfigured) {
        resetMissingTokenTests();
        return;
      }
      setConnectionTestStatus({ state: "checking", message: "Testing Pixiv API connection." });
      try {
        const response = await testPixivConnection();
        setConnectionTestStatus({ state: "valid", message: response.message, checkedAt: new Date() });
        if (notify) {
          pushToast({ title: "Pixiv connection verified", description: response.message, tone: "success" });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Pixiv API connection could not be verified.";
        setConnectionTestStatus({ state: "invalid", message, checkedAt: new Date() });
        if (notify) {
          pushToast({ title: "Pixiv connection failed", description: message, tone: "error" });
        }
      }
    },
    [pushToast, refreshTokenConfigured, resetMissingTokenTests]
  );

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
          resetCurrentTokenTests();
          void refreshSettings();
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
  }, [browserAuthFlow, pushToast, refreshSettings, remindToStopAuthBrowserIfRunning, resetCurrentTokenTests]);

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
      resetCurrentTokenTests();
      void refreshSettings();
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
      resetCurrentTokenTests();
      void refreshSettings();
      void remindToStopAuthBrowserIfRunning();
    },
    onError: (error) => pushToast({ title: "Pixiv sign-in failed", description: error.message, tone: "error" })
  });

  const refreshAuthMutation = useMutation({
    mutationFn: refreshPixivAuth,
    onSuccess: (response) => {
      pushToast({ title: "Pixiv token refreshed", description: response.message, tone: "success" });
      resetCurrentTokenTests();
      void refreshSettings();
    },
    onError: (error) => pushToast({ title: "Pixiv token refresh failed", description: error.message, tone: "error" })
  });

  const importLegacyDatabaseMutation = useMutation({
    mutationFn: importLegacyDatabase,
    onSuccess: (response) => {
      const runMessage = response.workflow_run_id ? ` Run: ${response.workflow_run_id}.` : "";
      const jobMessage = response.import_job_id ? ` Import job: ${response.import_job_id}.` : "";
      pushToast({
        title: "Legacy import started",
        description: `${response.message}${runMessage}${jobMessage}`,
        tone: "success"
      });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["workflow-runs"] });
    },
    onError: (error) => pushToast({ title: "Legacy database import failed", description: error.message, tone: "error" })
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
                { value: "appearance", label: "Appearance" },
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

            <React.Suspense fallback={<DataState title="Loading settings tab" variant="loading" />}>
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
                  authTestStatus={authTestStatus}
                  connectionTestStatus={connectionTestStatus}
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
                  onRunAuthTest={() => void runAuthTest({ notify: true })}
                  onRunConnectionTest={() => void runConnectionTest({ notify: true })}
                  onSaveManualToken={saveManualToken}
                  onStartBrowserAuth={() => startBrowserAuthMutation.mutate()}
                  onToggleToken={() => setShowToken((value) => !value)}
                />
              ) : null}

              {activeTab === "appearance" ? (
                <AppearanceSettingsTab
                  activePreset={activeThemePreset}
                  customPresets={customThemePresets}
                  settings={appearanceSettings}
                  onCreatePreset={createThemePreset}
                  onDeletePreset={deleteThemePreset}
                  onSetActivePreset={setActiveThemePreset}
                  onSetFollowSystem={setFollowSystemTheme}
                  onSetSystemPreset={setSystemThemePreset}
                  onUpdatePreset={updateThemePreset}
                />
              ) : null}

              {activeTab === "advanced" ? (
                <AdvancedSettingsTab
                  importLegacyDatabaseData={importLegacyDatabaseMutation.data}
                  isImporting={importLegacyDatabaseMutation.isPending}
                  legacyDatabaseInputId={legacyDatabaseInputId}
                  onImportLegacyDatabase={(file) => importLegacyDatabaseMutation.mutate(file)}
                  onRequestLegacyImport={() => setLegacyImportDialogOpen(true)}
                />
              ) : null}
            </React.Suspense>
          </div>
        )}
      </div>
      <LegacyImportConfirmDialog
        open={legacyImportDialogOpen}
        inputId={legacyDatabaseInputId}
        onOpenChange={setLegacyImportDialogOpen}
      />
      <AuthBrowserCommandDialog
        dialog={authBrowserDialog}
        onClose={() => setAuthBrowserDialog(null)}
        onCopy={(command) => {
          void copyCommand(command)
            .then(() => pushToast({ title: "Command copied", tone: "success" }))
            .catch((error: Error) => pushToast({ title: "Command copy failed", description: error.message, tone: "error" }));
        }}
        onUseManual={() => {
          setAuthBrowserDialog(null);
          startManualAuthMutation.mutate();
        }}
      />
    </>
  );
}

function LegacyImportConfirmDialog({
  open,
  inputId,
  onOpenChange
}: {
  open: boolean;
  inputId: string;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  return (
    <Dialog
      open={open}
      title="Import legacy database"
      description="This will start a full legacy hydration job after import. Pixiv metadata will be scanned for imported artists, but files will not be downloaded."
      onOpenChange={onOpenChange}
      footer={
        <>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() => {
              onOpenChange(false);
              document.getElementById(inputId)?.click();
            }}
          >
            <DatabaseBackup className="h-4 w-4" aria-hidden="true" />
            Continue Import
          </Button>
        </>
      }
    />
  );
}

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
