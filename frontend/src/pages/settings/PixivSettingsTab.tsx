import { AlertTriangle, CheckCircle2, ExternalLink, Eye, EyeOff, KeyRound, Loader2, RefreshCw, ShieldCheck } from "lucide-react";

import type { PixivAuthStartResponse, PixivBrowserAuthStartResponse, SettingsResponse } from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, formatCheckedAt, SettingsSection, type TestStatus } from "@/pages/settings/shared";

export type PixivSettingsTabProps = {
  authCode: string;
  authFlow: PixivAuthStartResponse | null;
  authTestStatus: TestStatus;
  browserAuthFlow: PixivBrowserAuthStartResponse | null;
  connectionTestStatus: TestStatus;
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
  onAuthCodeChange: (value: string) => void;
  onCancelAuthFlow: () => void;
  onCompleteAuth: () => void;
  onDismissBrowserFlow: () => void;
  onOpenBrowserFlow: () => void;
  onOpenContinueUrl: () => void;
  onRefreshAuth: () => void;
  onRefreshTokenChange: (value: string) => void;
  onRunAuthTest: () => void;
  onRunConnectionTest: () => void;
  onSaveManualToken: () => void;
  onStartBrowserAuth: () => void;
  onToggleToken: () => void;
};

export function PixivSettingsTab({
  authCode,
  authFlow,
  authTestStatus,
  browserAuthFlow,
  connectionTestStatus,
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
  onAuthCodeChange,
  onCancelAuthFlow,
  onCompleteAuth,
  onDismissBrowserFlow,
  onOpenBrowserFlow,
  onOpenContinueUrl,
  onRefreshAuth,
  onRefreshTokenChange,
  onRunAuthTest,
  onRunConnectionTest,
  onSaveManualToken,
  onStartBrowserAuth,
  onToggleToken
}: PixivSettingsTabProps): JSX.Element {
  return (
    <div className="mt-5 divide-y">
      <SettingsSection title="Pixiv authentication" description="Sign in, renew, or replace the saved Pixiv refresh token.">
        <div className="space-y-4">
          <Field
            label="New refresh token"
            tooltip="Paste a new Pixiv OAuth refresh token. Saved tokens are masked in normal settings responses."
            help={settings.refresh_token_configured ? `Saved token: ${settings.refresh_token_preview}` : "No saved token"}
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
            </div>
            <span className="mt-2 block text-xs leading-5 text-muted-foreground">
              Refresh Token asks Pixiv for a fresh token pair and saves the returned refresh token. Use it when the saved token works but you want to renew it without signing in again.
            </span>

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

      <SettingsSection title="Test Auth" description="Manually verify that the saved refresh token can authenticate.">
        <PixivTestStatus
          status={authTestStatus}
          preview={settings.refresh_token_preview}
          actionLabel="Test Auth"
          actionTitle="Verify that the configured Pixiv refresh token can authenticate."
          disabled={!settings.refresh_token_configured || authTestStatus.state === "checking"}
          icon="shield"
          onAction={onRunAuthTest}
        />
      </SettingsSection>

      <SettingsSection title="Test Connection" description="Manually call Pixiv user_detail with the authenticated account.">
        <PixivTestStatus
          status={connectionTestStatus}
          preview=""
          actionLabel="Test Connection"
          actionTitle="Run one real Pixiv API request to check restrictions, rate limits, or API availability."
          disabled={!settings.refresh_token_configured || connectionTestStatus.state === "checking"}
          icon="refresh"
          onAction={onRunConnectionTest}
        />
      </SettingsSection>
    </div>
  );
}

function PixivTestStatus({
  status,
  preview,
  actionLabel,
  actionTitle,
  disabled,
  icon,
  onAction
}: {
  status: TestStatus;
  preview: string;
  actionLabel: string;
  actionTitle: string;
  disabled: boolean;
  icon: "shield" | "refresh";
  onAction: () => void;
}): JSX.Element {
  const Icon = status.state === "checking" ? Loader2 : status.state === "valid" ? CheckCircle2 : AlertTriangle;
  const ActionIcon = icon === "shield" ? ShieldCheck : RefreshCw;
  const label =
    status.state === "valid"
      ? "Verified"
      : status.state === "checking"
        ? "Checking"
        : status.state === "invalid"
          ? "Needs attention"
          : status.state === "untested"
            ? "Not tested"
            : "Token not configured";
  const className =
    status.state === "valid"
      ? "status-success"
      : status.state === "checking"
        ? "border-border bg-muted/30 text-foreground"
        : "status-warning";

  return (
    <div className={`rounded-md border p-3 ${className}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <Icon
            className={`mt-0.5 h-5 w-5 shrink-0 ${status.state === "checking" ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          <div className="min-w-0">
            <span className="block text-sm font-semibold">{label}</span>
            <span className="mt-1 block text-sm leading-5">{status.message}</span>
            {preview ? <span className="mt-1 block text-xs opacity-75">Saved token: {preview}</span> : null}
            {status.checkedAt ? (
              <span className="mt-1 block text-xs opacity-75">Last checked: {formatCheckedAt(status.checkedAt)}</span>
            ) : null}
          </div>
        </div>
        <Button type="button" variant="outline" title={actionTitle} disabled={disabled} onClick={onAction}>
          <ActionIcon className="h-4 w-4" aria-hidden="true" />
          {actionLabel}
        </Button>
      </div>
    </div>
  );
}
