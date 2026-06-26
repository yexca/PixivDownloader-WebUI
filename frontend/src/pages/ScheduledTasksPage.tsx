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
  type ScheduledTaskAction
} from "@/api/scheduledTasks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { useToast } from "@/components/ToastProvider";
import { formatDate } from "@/lib/utils";

type FormState = {
  name: string;
  action: ScheduledTaskAction;
  target_artist_id: string;
  interval_days: number;
  enabled: boolean;
  run_after_startup: boolean;
};

const initialForm: FormState = {
  name: "",
  action: "download_artist",
  target_artist_id: "",
  interval_days: 30,
  enabled: true,
  run_after_startup: true
};

const actionLabels: Record<ScheduledTaskAction, string> = {
  sync_artist: "Sync metadata",
  download_artist: "Download updates",
  retry_failed_artist: "Retry failed files"
};

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
        ...form,
        target_artist_id: form.target_artist_id.trim(),
        name: form.name.trim()
      }),
    onSuccess: () => {
      pushToast({ title: "Scheduled task created", tone: "success" });
      setForm(initialForm);
      setFieldError(null);
      void queryClient.invalidateQueries({ queryKey: ["scheduled-tasks"] });
    },
    onError: (error) => pushToast({ title: "Task could not be created", description: error.message, tone: "error" })
  });

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!/^\d+$/.test(form.target_artist_id.trim())) {
      setFieldError("Artist ID must contain digits only.");
      return;
    }
    if (!Number.isInteger(form.interval_days) || form.interval_days < 1) {
      setFieldError("Interval must be a whole number of at least 1.");
      return;
    }
    createMutation.mutate();
  };

  return (
    <>
      <PageHeader
        title="Schedules"
        description="Create recurring sync, download, and retry jobs for Pixiv artists."
        actions={
          <Button type="button" variant="outline" onClick={() => void tasks.refetch()} disabled={tasks.isFetching}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </Button>
        }
      />
      <div className="grid gap-4 p-4 sm:p-6 xl:grid-cols-[420px_minmax(0,1fr)]">
        <form className="surface space-y-4 p-4" onSubmit={submit}>
          <div>
            <h2 className="text-sm font-semibold">New Schedule</h2>
          </div>
          <Field label="Name">
            <Input
              value={form.name}
              placeholder="Monthly artist updates"
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
          <Field label="Action">
            <Select
              value={form.action}
              onChange={(event) => setForm({ ...form, action: event.target.value as ScheduledTaskAction })}
            >
              {Object.entries(actionLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Pixiv artist ID" error={fieldError ?? undefined}>
            <Input
              inputMode="numeric"
              value={form.target_artist_id}
              placeholder="123456"
              aria-invalid={Boolean(fieldError)}
              onChange={(event) => setForm({ ...form, target_artist_id: event.target.value })}
            />
          </Field>
          <Field label="Interval days">
            <Input
              type="number"
              min={1}
              step={1}
              value={form.interval_days}
              onChange={(event) => setForm({ ...form, interval_days: Math.max(1, Number(event.target.value)) })}
            />
          </Field>
          <div className="space-y-3 rounded-md border bg-muted/30 p-3">
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
              Run missed schedule after startup
            </label>
          </div>
          <Button type="submit" className="w-full" disabled={createMutation.isPending}>
            <CalendarClock className="h-4 w-4" aria-hidden="true" />
            Create Schedule
          </Button>
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
        title: response.created ? "Job queued" : response.skipped ? "Schedule skipped" : "Schedule checked",
        description: response.job_id ?? response.task.last_error_message ?? undefined,
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
            {actionLabels[task.action]} · User {task.target_artist_id} · every {task.interval_days} days
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
        <Detail label="Last job" value={task.last_job_id ?? "-"} />
      </dl>
      {blocked && task.last_error_message ? (
        <p className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          {task.last_error_message}
        </p>
      ) : null}
    </article>
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
