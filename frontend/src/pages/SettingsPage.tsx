import * as React from "react";
import { Eye, EyeOff, Save, Undo2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getSettings, updateSettings, type SettingsResponse, type SettingsUpdateRequest } from "@/api/settings";
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

  React.useEffect(() => {
    if (settings.data && !form) {
      setForm(toForm(settings.data));
    }
  }, [settings.data, form]);

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

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form) {
      return;
    }
    const nextErrors = validate(form);
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
          <form className="surface max-w-3xl space-y-5 p-4" onSubmit={submit}>
            <Field label="Download path" error={errors.download_path}>
              <Input
                value={form.download_path}
                onChange={(event) => setForm({ ...form, download_path: event.target.value })}
              />
            </Field>

            <Field
              label="Refresh token"
              error={errors.refresh_token}
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

            <div className="grid gap-4 sm:grid-cols-3">
              <NumberField
                label="Base delay seconds"
                value={form.request_base_delay_seconds}
                error={errors.request_base_delay_seconds}
                onChange={(value) => setForm({ ...form, request_base_delay_seconds: value })}
              />
              <NumberField
                label="Random delay seconds"
                value={form.request_random_delay_seconds}
                error={errors.request_random_delay_seconds}
                onChange={(value) => setForm({ ...form, request_random_delay_seconds: value })}
              />
              <NumberField
                label="Max concurrent"
                value={form.max_concurrent_downloads}
                error={errors.max_concurrent_downloads}
                step={1}
                onChange={(value) => setForm({ ...form, max_concurrent_downloads: value })}
              />
            </div>

            <div className="grid gap-3 rounded-md border bg-muted/30 p-3 sm:grid-cols-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.skip_existing_files}
                  onChange={(event) => setForm({ ...form, skip_existing_files: event.target.checked })}
                />
                Skip existing files
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.overwrite_existing_files}
                  onChange={(event) => setForm({ ...form, overwrite_existing_files: event.target.checked })}
                />
                Overwrite existing files
              </label>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={mutation.isPending}>
                <Save className="h-4 w-4" aria-hidden="true" />
                Save
              </Button>
              <Button type="button" variant="outline" onClick={() => setForm(toForm(settings.data))}>
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

function validate(form: SettingsForm): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.download_path.trim()) {
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

function Field({
  label,
  children,
  error,
  help
}: {
  label: string;
  children: React.ReactNode;
  error?: string;
  help?: string;
}): JSX.Element {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-medium">{label}</span>
      {children}
      {help ? <span className="mt-1 block text-xs text-muted-foreground">{help}</span> : null}
      {error ? <span className="mt-1 block text-sm text-destructive">{error}</span> : null}
    </label>
  );
}

function NumberField({
  label,
  value,
  error,
  onChange,
  step = 0.1
}: {
  label: string;
  value: number;
  error?: string;
  onChange: (value: number) => void;
  step?: number;
}): JSX.Element {
  return (
    <Field label={label} error={error}>
      <Input
        type="number"
        min={0}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </Field>
  );
}
