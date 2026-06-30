import { Save, Undo2 } from "lucide-react";

import type { BasicForm } from "@/pages/settings/shared";
import type { SettingsResponse, SettingsUpdateRequest } from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SettingsActions, SettingsSection, Field, NumberField } from "@/pages/settings/shared";

export type BasicSettingsTabProps = {
  form: BasicForm;
  settings: SettingsResponse;
  errors: Record<string, string>;
  isSaving: boolean;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onChange: (form: BasicForm) => void;
  onReset: () => void;
};

export function BasicSettingsTab({
  form,
  settings,
  errors,
  isSaving,
  onSubmit,
  onChange,
  onReset
}: BasicSettingsTabProps): JSX.Element {
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
          <div className="grid gap-2 rounded-md border bg-muted/30 p-2 sm:grid-cols-3">
            {[
              { value: "skip", label: "Skip", title: "Leave existing files untouched and mark them as skipped." },
              { value: "overwrite", label: "Overwrite", title: "Replace files that already exist at the target path." },
              {
                value: "save_duplicate",
                label: "Save duplicate",
                title: "Keep existing files and save new downloads with numbered names."
              }
            ].map((item) => (
              <button
                key={item.value}
                type="button"
                className={
                  form.existing_file_behavior === item.value
                    ? "rounded-md border border-primary bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
                    : "rounded-md border bg-background px-3 py-2 text-sm font-medium hover:bg-muted"
                }
                title={item.title}
                onClick={() =>
                  onChange({
                    ...form,
                    existing_file_behavior: item.value as SettingsUpdateRequest["existing_file_behavior"]
                  })
                }
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title="Requests and performance" description="Tune Pixiv API pacing, file download pacing, and job concurrency.">
        <div className="space-y-3">
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField
              label="API base delay seconds"
              value={form.request_base_delay_seconds}
              error={errors.request_base_delay_seconds}
              tooltip="Fixed minimum wait before each Pixiv metadata API request."
              onChange={(value) => onChange({ ...form, request_base_delay_seconds: value })}
            />
            <NumberField
              label="API random delay seconds"
              value={form.request_random_delay_seconds}
              error={errors.request_random_delay_seconds}
              tooltip="Extra random wait from 0 up to this many seconds before metadata API requests."
              onChange={(value) => onChange({ ...form, request_random_delay_seconds: value })}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField
              label="File base delay seconds"
              value={form.file_download_base_delay_seconds}
              error={errors.file_download_base_delay_seconds}
              tooltip="Fixed minimum wait before each real Pixiv image file download."
              onChange={(value) => onChange({ ...form, file_download_base_delay_seconds: value })}
            />
            <NumberField
              label="File random delay seconds"
              value={form.file_download_random_delay_seconds}
              error={errors.file_download_random_delay_seconds}
              tooltip="Extra random wait from 0 up to this many seconds before image file downloads."
              onChange={(value) => onChange({ ...form, file_download_random_delay_seconds: value })}
            />
          </div>
          <p className="text-xs leading-5 text-muted-foreground">
            Existing local files are skipped without waiting. Retryable 429 and 5xx responses use a separate backoff schedule.
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
              label="Schedule trigger limit"
              value={form.max_active_scheduled_tasks}
              error={errors.max_active_scheduled_tasks}
              min={1}
              step={1}
              tooltip="Legacy compatibility setting. Schedules now act as triggers; run execution capacity is controlled by the run limit."
              onChange={(value) => onChange({ ...form, max_active_scheduled_tasks: Math.max(1, Math.trunc(value)) })}
            />
            <NumberField
              label="Run limit"
              value={form.max_active_run_jobs}
              error={errors.max_active_run_jobs}
              min={1}
              step={1}
              tooltip="Maximum number of workflow run jobs allowed to wait or run. Extra run jobs stay inactive."
              onChange={(value) => onChange({ ...form, max_active_run_jobs: Math.max(1, Math.trunc(value)) })}
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
