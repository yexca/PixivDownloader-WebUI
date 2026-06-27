import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CheckCircle2, Pause, Play, RefreshCw, Trash2, X } from "lucide-react";

import {
  createScheduledTask,
  deleteScheduledTask,
  listScheduledTasks,
  runScheduledTask,
  updateScheduledTask,
  type ScheduledTask,
  type ScheduledTaskAction,
  type ScheduledTaskArtistSelection,
  type ScheduledTaskConfig,
  type ScheduledTaskFilterType,
  type ScheduledTaskTargetType
} from "@/api/scheduledTasks";
import { listLocalTags, type LocalTag } from "@/api/artists";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { useToast } from "@/components/ToastProvider";
import { cn, formatDate } from "@/lib/utils";

type FormState = {
  name: string;
  interval_days: number;
  enabled: boolean;
  run_after_startup: boolean;
  target_type: ScheduledTaskTargetType;
  artist_id: string;
  tags: string[];
  stale_target_days: number;
  filters: ScheduledTaskFilterType[];
  stale_filter_days: number;
  actions: ScheduledTaskAction[];
  max_artists_per_run: number;
  artist_selection: ScheduledTaskArtistSelection;
};

type FormField = "artist_id" | "tag" | "interval_days" | "max_artists_per_run" | "stale_target_days" | "stale_filter_days" | "actions";
type TouchedFields = Partial<Record<FormField, boolean>>;
type FieldState = "neutral" | "valid" | "invalid";

const initialForm: FormState = {
  name: "",
  interval_days: 30,
  enabled: true,
  run_after_startup: true,
  target_type: "single_artist",
  artist_id: "",
  tags: [],
  stale_target_days: 30,
  filters: [],
  stale_filter_days: 30,
  actions: ["download_artist"],
  max_artists_per_run: 25,
  artist_selection: "oldest_checked_first"
};

const actionLabels: Record<ScheduledTaskAction, string> = {
  sync_artist: "Sync metadata",
  download_artist: "Download updates",
  retry_failed_artist: "Retry failed files"
};

const targetLabels: Record<ScheduledTaskTargetType, string> = {
  single_artist: "Single artist",
  all_artists: "All artists",
  artists_with_tag: "Artists with tag",
  artists_not_checked: "Artists not checked"
};

const filterLabels: Record<ScheduledTaskFilterType, string> = {
  last_checked_before_days: "Last checked before",
  has_failed_files: "Has failed files"
};

const artistSelectionLabels: Record<ScheduledTaskArtistSelection, string> = {
  oldest_checked_first: "Oldest checked first",
  newest_checked_first: "Newest checked first",
  random: "Random"
};

const ACTION_ERROR = "Select at least one action.";

export function ScheduledTasksPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [form, setForm] = React.useState<FormState>(initialForm);
  const [touched, setTouched] = React.useState<TouchedFields>({});
  const [submitted, setSubmitted] = React.useState(false);
  const [tagSearch, setTagSearch] = React.useState("");
  const [tagPickerOpen, setTagPickerOpen] = React.useState(false);
  const errors = validateForm(form);
  const firstError = firstFormError(errors);
  const isValid = firstError === null;
  const markTouched = (field: FormField) =>
    setTouched((current) => ({ ...current, [field]: true }));
  const fieldMeta = (field: FormField) => validationMeta(field, errors, touched, submitted);
  const intervalMeta = fieldMeta("interval_days");
  const maxArtistsMeta = fieldMeta("max_artists_per_run");
  const artistIdMeta = fieldMeta("artist_id");
  const tagMeta = fieldMeta("tag");
  const staleTargetMeta = fieldMeta("stale_target_days");
  const staleFilterMeta = fieldMeta("stale_filter_days");
  const actionsMeta = fieldMeta("actions");
  const tasks = useQuery({
    queryKey: ["scheduled-tasks"],
    queryFn: listScheduledTasks,
    refetchInterval: 15000
  });
  const localTags = useQuery({
    queryKey: ["local-tags"],
    queryFn: listLocalTags
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createScheduledTask({
        name: form.name.trim(),
        action: form.actions[0],
        target_artist_id: form.target_type === "single_artist" ? form.artist_id.trim() : null,
        interval_days: form.interval_days,
        enabled: form.enabled,
        run_after_startup: form.run_after_startup,
        config: formToConfig(form)
      }),
    onSuccess: () => {
      pushToast({ title: "Scheduled task created", tone: "success" });
      setForm(initialForm);
      setTouched({});
      setSubmitted(false);
      void queryClient.invalidateQueries({ queryKey: ["scheduled-tasks"] });
    },
    onError: (error) =>
      pushToast({ title: "Task could not be created", description: error.message, tone: "error" })
  });

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
    if (firstError) {
      return;
    }
    createMutation.mutate();
  };

  return (
    <>
      <PageHeader
        title="Schedules"
        description="Build recurring artist workflows from target, filter, and action modules."
        actions={
          <Button type="button" variant="outline" onClick={() => void tasks.refetch()} disabled={tasks.isFetching}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </Button>
        }
      />
      <div className="grid gap-4 p-4 sm:p-6 xl:grid-cols-[460px_minmax(0,1fr)]">
        <form className="space-y-4" onSubmit={submit}>
          <section className="surface space-y-4 p-4">
            <div>
              <h2 className="text-sm font-semibold">Workflow</h2>
            </div>
            <Field label="Name" description="Optional. Leave blank to use an automatic schedule name.">
              <Input
                value={form.name}
                placeholder="Monthly favorite updates"
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Interval days" {...intervalMeta}>
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={form.interval_days}
                  className={fieldClassName(intervalMeta.state)}
                  aria-invalid={intervalMeta.state === "invalid"}
                  onChange={(event) =>
                    setForm({ ...form, interval_days: Number(event.target.value) })
                  }
                  onBlur={() => markTouched("interval_days")}
                />
              </Field>
              <Field label="Artist selection">
                <Select
                  value={form.artist_selection}
                  onChange={(event) =>
                    setForm({ ...form, artist_selection: event.target.value as ScheduledTaskArtistSelection })
                  }
                >
                  {Object.entries(artistSelectionLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Max artists per run" {...maxArtistsMeta}>
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={form.max_artists_per_run}
                  className={fieldClassName(maxArtistsMeta.state)}
                  aria-invalid={maxArtistsMeta.state === "invalid"}
                  onChange={(event) =>
                    setForm({ ...form, max_artists_per_run: Number(event.target.value) })
                  }
                  onBlur={() => markTouched("max_artists_per_run")}
                />
              </Field>
            </div>
            <div className="grid gap-3 rounded-md border bg-muted/30 p-3 sm:grid-cols-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
                />
                Enabled
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.run_after_startup}
                  onChange={(event) => setForm({ ...form, run_after_startup: event.target.checked })}
                />
                Run on restart
              </label>
            </div>
          </section>

          <section className="surface space-y-4 p-4">
            <h2 className="text-sm font-semibold">Target</h2>
            <Field label="Target type">
              <Select
                value={form.target_type}
                onChange={(event) =>
                  setForm({ ...form, target_type: event.target.value as ScheduledTaskTargetType })
                }
              >
                {Object.entries(targetLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            {form.target_type === "single_artist" ? (
              <Field label="Pixiv artist ID" {...artistIdMeta}>
                <Input
                  inputMode="numeric"
                  value={form.artist_id}
                  placeholder="123456"
                  className={fieldClassName(artistIdMeta.state)}
                  aria-invalid={artistIdMeta.state === "invalid"}
                  onChange={(event) => {
                    markTouched("artist_id");
                    setForm({ ...form, artist_id: event.target.value });
                  }}
                  onBlur={() => markTouched("artist_id")}
                />
              </Field>
            ) : null}
            {form.target_type === "artists_with_tag" ? (
              <Field label="Local tag" {...tagMeta}>
                <TagMultiSelect
                  tags={localTags.data?.items ?? []}
                  selectedTags={form.tags}
                  search={tagSearch}
                  open={tagPickerOpen}
                  state={tagMeta.state}
                  loading={localTags.isLoading}
                  onSearchChange={(value) => {
                    markTouched("tag");
                    setTagSearch(value);
                    setTagPickerOpen(true);
                  }}
                  onOpenChange={(open) => {
                    setTagPickerOpen(open);
                    if (!open) {
                      markTouched("tag");
                    }
                  }}
                  onSelect={(tag) => {
                    markTouched("tag");
                    setForm({ ...form, tags: toggleItem(form.tags, tag, true) });
                    setTagSearch("");
                    setTagPickerOpen(true);
                  }}
                  onRemove={(tag) => {
                    markTouched("tag");
                    setForm({ ...form, tags: toggleItem(form.tags, tag, false) });
                  }}
                />
              </Field>
            ) : null}
            {form.target_type === "artists_not_checked" ? (
              <Field label="Not checked for days" {...staleTargetMeta}>
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={form.stale_target_days}
                  className={fieldClassName(staleTargetMeta.state)}
                  aria-invalid={staleTargetMeta.state === "invalid"}
                  onChange={(event) =>
                    setForm({ ...form, stale_target_days: Number(event.target.value) })
                  }
                  onBlur={() => markTouched("stale_target_days")}
                />
              </Field>
            ) : null}
          </section>

          <section className="surface space-y-4 p-4">
            <h2 className="text-sm font-semibold">Filters</h2>
            <ModuleCheckbox
              checked={form.filters.includes("last_checked_before_days")}
              label={filterLabels.last_checked_before_days}
              onChange={(checked) => setForm({ ...form, filters: toggleItem(form.filters, "last_checked_before_days", checked) })}
            />
            {form.filters.includes("last_checked_before_days") ? (
              <Field label="Older than days" {...staleFilterMeta}>
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={form.stale_filter_days}
                  className={fieldClassName(staleFilterMeta.state)}
                  aria-invalid={staleFilterMeta.state === "invalid"}
                  onChange={(event) =>
                    setForm({ ...form, stale_filter_days: Number(event.target.value) })
                  }
                  onBlur={() => markTouched("stale_filter_days")}
                />
              </Field>
            ) : null}
            <ModuleCheckbox
              checked={form.filters.includes("has_failed_files")}
              label={filterLabels.has_failed_files}
              onChange={(checked) => setForm({ ...form, filters: toggleItem(form.filters, "has_failed_files", checked) })}
            />
          </section>

          <section
            className={cn(
              "surface space-y-4 p-4 transition-colors",
              actionsMeta.state === "invalid" && "border-destructive/60",
              actionsMeta.state === "valid" && "border-emerald-500/30"
            )}
          >
            <h2 className="text-sm font-semibold">Actions</h2>
            {(Object.keys(actionLabels) as ScheduledTaskAction[]).map((action) => (
              <ModuleCheckbox
                key={action}
                checked={form.actions.includes(action)}
                label={actionLabels[action]}
                onChange={(checked) => {
                  markTouched("actions");
                  setForm({ ...form, actions: toggleItem(form.actions, action, checked) });
                }}
              />
            ))}
            {actionsMeta.state === "invalid" ? <p className="text-sm text-destructive">{ACTION_ERROR}</p> : null}
            {actionsMeta.state === "valid" ? (
              <p className="flex items-center gap-1.5 text-sm text-emerald-700">
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                Actions selected
              </p>
            ) : null}
          </section>

          <section className="surface p-4">
            <h2 className="text-sm font-semibold">Preview</h2>
            {isValid ? (
              <p className="mt-2 text-sm text-muted-foreground">{previewText(form)}</p>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">{firstError}</p>
            )}
            {isValid ? (
              <p className="mt-3 flex items-center gap-1.5 text-sm text-emerald-700">
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                Ready to create
              </p>
            ) : null}
            <Button type="submit" className="mt-4 w-full" disabled={createMutation.isPending || !isValid}>
              <CalendarClock className="h-4 w-4" aria-hidden="true" />
              Create Schedule
            </Button>
          </section>
        </form>

        <section>
          {tasks.isLoading ? (
            <DataState title="Loading schedules" variant="loading" />
          ) : tasks.isError ? (
            <DataState title="Could not load schedules" description={tasks.error.message} variant="error" />
          ) : tasks.data.items.length === 0 ? (
            <DataState title="No schedules" description="Create a schedule to queue recurring artist work." />
          ) : (
            <div className="grid gap-3">
              {tasks.data.items.map((task) => (
                <TaskRow key={task.id} task={task} />
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}

function TaskRow({ task }: { task: ScheduledTask }): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["scheduled-tasks"] });
  const runMutation = useMutation({
    mutationFn: () => runScheduledTask(task.id),
    onSuccess: (response) => {
      pushToast({
        title: response.created ? "Jobs queued" : response.skipped ? "Schedule skipped" : "Schedule checked",
        description: response.job_ids.length ? `${response.job_ids.length} job(s)` : response.task.last_error_message ?? undefined,
        tone: response.task.status === "blocked" ? "error" : "success"
      });
      invalidate();
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Schedule could not run", description: error.message, tone: "error" })
  });
  const statusMutation = useMutation({
    mutationFn: (status: ScheduledTask["status"]) => updateScheduledTask(task.id, { status }),
    onSuccess: invalidate,
    onError: (error) => pushToast({ title: "Schedule could not be updated", description: error.message, tone: "error" })
  });
  const deleteMutation = useMutation({
    mutationFn: () => deleteScheduledTask(task.id),
    onSuccess: () => {
      pushToast({ title: "Schedule deleted", tone: "success" });
      invalidate();
    },
    onError: (error) => pushToast({ title: "Schedule could not be deleted", description: error.message, tone: "error" })
  });
  const blocked = task.status === "blocked";

  return (
    <article className="surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-sm font-semibold">{task.name}</h2>
            <StatusPill status={task.status} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {taskSummary(task)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
            <Play className="h-4 w-4" aria-hidden="true" />
            Run
          </Button>
          {task.status === "active" ? (
            <Button type="button" size="sm" variant="outline" onClick={() => statusMutation.mutate("paused")}>
              <Pause className="h-4 w-4" aria-hidden="true" />
              Pause
            </Button>
          ) : (
            <Button type="button" size="sm" variant="outline" onClick={() => statusMutation.mutate("active")}>
              <Play className="h-4 w-4" aria-hidden="true" />
              Resume
            </Button>
          )}
          <Button type="button" size="sm" variant="outline" onClick={() => deleteMutation.mutate()}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            Delete
          </Button>
        </div>
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-4">
        <Detail label="Next run" value={formatDate(task.next_run_at)} />
        <Detail label="Last run" value={formatDate(task.last_run_at)} />
        <Detail label="Last success" value={formatDate(task.last_success_at)} />
        <Detail label="Last jobs" value={lastJobCount(task)} />
      </dl>
      {blocked && task.last_error_message ? (
        <p className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          {task.last_error_message}
        </p>
      ) : null}
    </article>
  );
}

function formToConfig(form: FormState): ScheduledTaskConfig {
  return {
    target: {
      type: form.target_type,
      artist_id: form.target_type === "single_artist" ? form.artist_id.trim() : null,
      tag: form.target_type === "artists_with_tag" ? form.tags[0] ?? null : null,
      tags: form.target_type === "artists_with_tag" ? form.tags : [],
      days: form.target_type === "artists_not_checked" ? form.stale_target_days : null
    },
    filters: form.filters.map((filter) => ({
      type: filter,
      days: filter === "last_checked_before_days" ? form.stale_filter_days : null
    })),
    actions: form.actions,
    max_artists_per_run: form.max_artists_per_run,
    artist_selection: form.artist_selection
  };
}

function validateForm(form: FormState): Partial<Record<FormField, string>> {
  const errors: Partial<Record<FormField, string>> = {};
  if (!isPositiveInteger(form.interval_days)) {
    errors.interval_days = "Interval days must be at least 1.";
  }
  if (!isPositiveInteger(form.max_artists_per_run)) {
    errors.max_artists_per_run = "Max artists per run must be at least 1.";
  }
  if (form.target_type === "single_artist" && !/^\d+$/.test(form.artist_id.trim())) {
    errors.artist_id = "Artist ID must contain digits only.";
  }
  if (form.target_type === "artists_with_tag" && form.tags.length === 0) {
    errors.tag = "Select at least one local tag.";
  }
  if (form.target_type === "artists_not_checked" && !isPositiveInteger(form.stale_target_days)) {
    errors.stale_target_days = "Not checked days must be at least 1.";
  }
  if (form.filters.includes("last_checked_before_days") && !isPositiveInteger(form.stale_filter_days)) {
    errors.stale_filter_days = "Filter days must be at least 1.";
  }
  if (form.actions.length === 0) {
    errors.actions = ACTION_ERROR;
  }
  return errors;
}

function firstFormError(errors: Partial<Record<FormField, string>>): string | null {
  const order: FormField[] = [
    "interval_days",
    "max_artists_per_run",
    "artist_id",
    "tag",
    "stale_target_days",
    "stale_filter_days",
    "actions"
  ];
  for (const field of order) {
    if (errors[field]) {
      return errors[field] ?? null;
    }
  }
  return null;
}

function validationMeta(
  field: FormField,
  errors: Partial<Record<FormField, string>>,
  touched: TouchedFields,
  submitted: boolean
): { state: FieldState; error?: string } {
  const showState = submitted || Boolean(touched[field]);
  if (!showState) {
    return { state: "neutral" };
  }
  if (errors[field]) {
    return { state: "invalid", error: errors[field] };
  }
  return { state: "valid" };
}

function isPositiveInteger(value: number): boolean {
  return Number.isInteger(value) && value >= 1;
}

function fieldClassName(state: FieldState): string {
  if (state === "invalid") {
    return "border-destructive/70 focus-visible:ring-destructive/30";
  }
  if (state === "valid") {
    return "border-emerald-500/50 focus-visible:ring-emerald-500/25";
  }
  return "";
}

function previewText(form: FormState): string {
  const target = targetLabels[form.target_type];
  const filters = form.filters.length ? form.filters.map((filter) => filterLabels[filter]).join(", ") : "no filters";
  const actions = form.actions.map((action) => actionLabels[action]).join(" then ");
  return `${target}, ${filters}, ${artistSelectionLabels[form.artist_selection]}, ${actions || "no actions"}, every ${form.interval_days} days.`;
}

function taskSummary(task: ScheduledTask): string {
  const config = task.config;
  const target = targetLabels[config.target.type] ?? config.target.type;
  const actions = config.actions.map((action) => actionLabels[action]).join(" then ");
  const selection = artistSelectionLabels[config.artist_selection] ?? config.artist_selection;
  return `${target} · ${selection} · ${actions} · every ${task.interval_days} days`;
}

function lastJobCount(task: ScheduledTask): string {
  const count = task.last_run_summary?.created_jobs;
  return typeof count === "number" ? String(count) : task.last_job_id ?? "-";
}

function toggleItem<T>(items: T[], item: T, checked: boolean): T[] {
  if (checked) {
    return items.includes(item) ? items : [...items, item];
  }
  return items.filter((value) => value !== item);
}

function TagMultiSelect({
  tags,
  selectedTags,
  search,
  open,
  state,
  loading,
  onSearchChange,
  onOpenChange,
  onSelect,
  onRemove
}: {
  tags: LocalTag[];
  selectedTags: string[];
  search: string;
  open: boolean;
  state: FieldState;
  loading: boolean;
  onSearchChange: (value: string) => void;
  onOpenChange: (open: boolean) => void;
  onSelect: (tag: string) => void;
  onRemove: (tag: string) => void;
}): JSX.Element {
  const query = search.trim().toLowerCase();
  const selectedKeys = new Set(selectedTags.map((tag) => tag.toLowerCase()));
  const options = tags
    .filter((tag) => !selectedKeys.has(tag.name.toLowerCase()))
    .filter((tag) => !query || tag.name.toLowerCase().includes(query));

  return (
    <div className="relative">
      {selectedTags.length ? (
        <div className="mb-2 flex flex-wrap gap-2">
          {selectedTags.map((tag) => (
            <span
              key={tag}
              className="inline-flex min-h-7 max-w-full items-center gap-1 rounded-md border border-emerald-500/25 bg-emerald-50 px-2 text-sm text-emerald-800"
            >
              <span className="truncate">{tag}</span>
              <button
                type="button"
                className="rounded-sm p-0.5 text-emerald-700 hover:bg-emerald-100"
                onClick={() => onRemove(tag)}
                aria-label={`Remove ${tag}`}
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <Input
        value={search}
        placeholder="Search local tags"
        className={fieldClassName(state)}
        aria-invalid={state === "invalid"}
        onFocus={() => onOpenChange(true)}
        onBlur={() => window.setTimeout(() => onOpenChange(false), 120)}
        onChange={(event) => onSearchChange(event.target.value)}
      />
      {open ? (
        <div className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border bg-background p-1 shadow-lg">
          {loading ? (
            <div className="px-3 py-2 text-sm text-muted-foreground">Loading tags...</div>
          ) : options.length ? (
            options.map((tag) => (
              <button
                key={tag.id}
                type="button"
                className="block w-full rounded-sm px-3 py-2 text-left text-sm hover:bg-muted"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => onSelect(tag.name)}
              >
                {tag.name}
              </button>
            ))
          ) : (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              {tags.length ? "No matching tags" : "No local tags yet"}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

function ModuleCheckbox({
  checked,
  label,
  onChange
}: {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}): JSX.Element {
  return (
    <label className="flex min-h-9 items-center gap-2 rounded-md border bg-muted/20 px-3 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
    </label>
  );
}

function StatusPill({ status }: { status: ScheduledTask["status"] }): JSX.Element {
  const tone = status === "active" ? "success" : status === "blocked" ? "danger" : "muted";
  return <Badge tone={tone}>{status}</Badge>;
}

function Field({
  label,
  error,
  description,
  state = "neutral",
  children
}: {
  label: string;
  error?: string;
  description?: string;
  state?: FieldState;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <label className="block text-sm">
      <span className="mb-2 flex items-center gap-1.5 font-medium">
        {label}
        {state === "valid" ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" /> : null}
      </span>
      {children}
      {description ? <span className="mt-2 block text-sm text-muted-foreground">{description}</span> : null}
      {error ? <span className="mt-2 block text-sm text-destructive">{error}</span> : null}
    </label>
  );
}

function Detail({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <dt className="text-xs uppercase text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words font-medium">{value}</dd>
    </div>
  );
}
