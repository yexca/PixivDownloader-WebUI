import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Pause, Play, RefreshCw, Trash2 } from "lucide-react";

import {
  createScheduledTask,
  deleteScheduledTask,
  listScheduledTasks,
  runScheduledTask,
  updateScheduledTask,
  type ScheduledTask,
  type ScheduledTaskAction,
  type ScheduledTaskConfig,
  type ScheduledTaskFilterType,
  type ScheduledTaskTargetType
} from "@/api/scheduledTasks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { useToast } from "@/components/ToastProvider";
import { formatDate } from "@/lib/utils";

type FormState = {
  name: string;
  interval_days: number;
  enabled: boolean;
  run_after_startup: boolean;
  target_type: ScheduledTaskTargetType;
  artist_id: string;
  tag: string;
  stale_target_days: number;
  filters: ScheduledTaskFilterType[];
  stale_filter_days: number;
  actions: ScheduledTaskAction[];
  max_artists_per_run: number;
};

const initialForm: FormState = {
  name: "",
  interval_days: 30,
  enabled: true,
  run_after_startup: true,
  target_type: "single_artist",
  artist_id: "",
  tag: "",
  stale_target_days: 30,
  filters: [],
  stale_filter_days: 30,
  actions: ["download_artist"],
  max_artists_per_run: 25
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

const ACTION_ERROR = "Select at least one action.";

export function ScheduledTasksPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [form, setForm] = React.useState<FormState>(initialForm);
  const [fieldError, setFieldError] = React.useState<string | null>(null);
  const tasks = useQuery({
    queryKey: ["scheduled-tasks"],
    queryFn: listScheduledTasks,
    refetchInterval: 15000
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createScheduledTask({
        name: form.name.trim(),
        action: form.actions[0],
        target_artist_id: form.target_type === "single_artist" ? form.artist_id.trim() : "",
        interval_days: form.interval_days,
        enabled: form.enabled,
        run_after_startup: form.run_after_startup,
        config: formToConfig(form)
      }),
    onSuccess: () => {
      pushToast({ title: "Scheduled task created", tone: "success" });
      setForm(initialForm);
      setFieldError(null);
      void queryClient.invalidateQueries({ queryKey: ["scheduled-tasks"] });
    },
    onError: (error) =>
      pushToast({ title: "Task could not be created", description: error.message, tone: "error" })
  });

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const error = validateForm(form);
    if (error) {
      setFieldError(error);
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
            <Field label="Name">
              <Input
                value={form.name}
                placeholder="Monthly favorite updates"
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Interval days">
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={form.interval_days}
                  onChange={(event) =>
                    setForm({ ...form, interval_days: Math.max(1, Number(event.target.value)) })
                  }
                />
              </Field>
              <Field label="Max artists per run">
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={form.max_artists_per_run}
                  onChange={(event) =>
                    setForm({ ...form, max_artists_per_run: Math.max(1, Number(event.target.value)) })
                  }
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
              <Field label="Pixiv artist ID" error={fieldError ?? undefined}>
                <Input
                  inputMode="numeric"
                  value={form.artist_id}
                  placeholder="123456"
                  aria-invalid={Boolean(fieldError)}
                  onChange={(event) => setForm({ ...form, artist_id: event.target.value })}
                />
              </Field>
            ) : null}
            {form.target_type === "artists_with_tag" ? (
              <Field label="Local tag" error={fieldError ?? undefined}>
                <Input
                  value={form.tag}
                  placeholder="favorite"
                  aria-invalid={Boolean(fieldError)}
                  onChange={(event) => setForm({ ...form, tag: event.target.value })}
                />
              </Field>
            ) : null}
            {form.target_type === "artists_not_checked" ? (
              <Field label="Not checked for days">
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={form.stale_target_days}
                  onChange={(event) =>
                    setForm({ ...form, stale_target_days: Math.max(1, Number(event.target.value)) })
                  }
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
              <Field label="Older than days">
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={form.stale_filter_days}
                  onChange={(event) =>
                    setForm({ ...form, stale_filter_days: Math.max(1, Number(event.target.value)) })
                  }
                />
              </Field>
            ) : null}
            <ModuleCheckbox
              checked={form.filters.includes("has_failed_files")}
              label={filterLabels.has_failed_files}
              onChange={(checked) => setForm({ ...form, filters: toggleItem(form.filters, "has_failed_files", checked) })}
            />
          </section>

          <section className={`surface space-y-4 p-4 ${fieldError === ACTION_ERROR ? "border-destructive" : ""}`}>
            <h2 className="text-sm font-semibold">Actions</h2>
            {(Object.keys(actionLabels) as ScheduledTaskAction[]).map((action) => (
              <ModuleCheckbox
                key={action}
                checked={form.actions.includes(action)}
                label={actionLabels[action]}
                onChange={(checked) => setForm({ ...form, actions: toggleItem(form.actions, action, checked) })}
              />
            ))}
            {fieldError === ACTION_ERROR ? <p className="text-sm text-destructive">{ACTION_ERROR}</p> : null}
          </section>

          <section className="surface p-4">
            <h2 className="text-sm font-semibold">Preview</h2>
            <p className="mt-2 text-sm text-muted-foreground">{previewText(form)}</p>
            {fieldError ? <p className="mt-3 text-sm text-destructive">{fieldError}</p> : null}
            <Button type="submit" className="mt-4 w-full" disabled={createMutation.isPending}>
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
      tag: form.target_type === "artists_with_tag" ? form.tag.trim() : null,
      days: form.target_type === "artists_not_checked" ? form.stale_target_days : null
    },
    filters: form.filters.map((filter) => ({
      type: filter,
      days: filter === "last_checked_before_days" ? form.stale_filter_days : null
    })),
    actions: form.actions,
    max_artists_per_run: form.max_artists_per_run
  };
}

function validateForm(form: FormState): string | null {
  if (form.target_type === "single_artist" && !/^\d+$/.test(form.artist_id.trim())) {
    return "Artist ID must contain digits only.";
  }
  if (form.target_type === "artists_with_tag" && !form.tag.trim()) {
    return "Local tag is required.";
  }
  if (form.actions.length === 0) {
    return ACTION_ERROR;
  }
  return null;
}

function previewText(form: FormState): string {
  const target = targetLabels[form.target_type];
  const filters = form.filters.length ? form.filters.map((filter) => filterLabels[filter]).join(", ") : "no filters";
  const actions = form.actions.map((action) => actionLabels[action]).join(" then ");
  return `${target}, ${filters}, ${actions || "no actions"}, every ${form.interval_days} days.`;
}

function taskSummary(task: ScheduledTask): string {
  const config = task.config;
  const target = targetLabels[config.target.type] ?? config.target.type;
  const actions = config.actions.map((action) => actionLabels[action]).join(" then ");
  return `${target} · ${actions} · every ${task.interval_days} days`;
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

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }): JSX.Element {
  return (
    <label className="block text-sm">
      <span className="mb-2 block font-medium">{label}</span>
      {children}
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
