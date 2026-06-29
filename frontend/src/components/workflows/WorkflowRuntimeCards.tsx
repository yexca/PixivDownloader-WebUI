import * as React from "react";
import { Play, Pause, RefreshCw, Trash2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { getJob, type Job, type JobDetail } from "@/api/jobs";
import {
  deleteScheduledTask,
  runScheduledTask,
  type ScheduledTask,
  updateScheduledTask
} from "@/api/scheduledTasks";
import type { SettingsResponse } from "@/api/settings";
import type { WorkflowBatchRun } from "@/api/workflows";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { DataState } from "@/components/DataState";
import { useToast } from "@/components/ToastProvider";
import { formatDate } from "@/lib/utils";
import {
  jobLabel,
  jobStatusTone,
  jobTarget,
  lastRunLabel,
  runTitle,
  scheduleSummary,
  sourceLabel,
  workflowItemTone,
  workflowJobStats,
  workflowRunTone
} from "./runtime";

export function RunWorkflowCard({ run, onInspect }: { run: WorkflowBatchRun; onInspect: () => void }): JSX.Element {
  return (
    <article className="surface p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-sm font-semibold">{runTitle(run)}</h2>
            <WorkflowRunStatusPill status={run.status} />
            <Badge tone="muted">run</Badge>
            {run.source === "schedule" || run.source === "manual_schedule" ? (
              <Badge tone="default">{run.source === "manual_schedule" ? "manual schedule" : "schedule"}</Badge>
            ) : null}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {run.completed}/{run.total} completed, {run.failed} failed, {run.skipped} skipped
          </p>
        </div>
        <div className="text-left text-sm text-muted-foreground sm:text-right">
          <div>{formatDate(run.created_at)}</div>
          <div className="mt-1">Concurrency {run.concurrency}</div>
          <Button type="button" size="sm" variant="outline" className="mt-2" onClick={onInspect}>
            Inspect
          </Button>
        </div>
      </div>
      <div className="mt-3 space-y-2">
        {run.items.map((item) => (
          <div key={item.id ?? item.draft_id} className="rounded-md border bg-muted/20 p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{item.title}</span>
              <Badge tone={workflowItemTone(item.status)}>{item.status}</Badge>
            </div>
            {item.job_ids.length ? (
              <p className="mt-1 break-all text-xs text-muted-foreground">
                {item.job_ids.length} job(s): {item.job_ids.join(", ")}
              </p>
            ) : item.error_message ? (
              <p className="mt-1 break-words text-xs text-destructive">{item.error_message}</p>
            ) : (
              <p className="mt-1 text-xs text-muted-foreground">No job was created.</p>
            )}
          </div>
        ))}
      </div>
    </article>
  );
}

export function WorkflowGroupSection({
  title,
  count,
  children
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}): JSX.Element {
  if (count === 0) {
    return (
      <section className="rounded-md border bg-muted/20 p-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{title}</h3>
          <Badge tone="muted">0</Badge>
        </div>
      </section>
    );
  }
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-2 px-1">
        <h3 className="text-sm font-semibold">{title}</h3>
        <Badge tone="muted">{count}</Badge>
      </div>
      <div className="grid gap-3">{children}</div>
    </section>
  );
}

export function WaitingJobCard({ job }: { job: Job }): JSX.Element {
  return (
    <article className="surface p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-sm font-semibold">{jobLabel(job)}</h2>
            <Badge tone="muted">waiting</Badge>
            {job.workflow_source ? <Badge tone="default">{sourceLabel(job.workflow_source)}</Badge> : null}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{jobTarget(job)}</p>
        </div>
        <div className="text-left text-sm text-muted-foreground sm:text-right">
          <div>{formatDate(job.created_at)}</div>
          <div className="mt-1">{job.completed_files}/{job.total_files || 0} files</div>
        </div>
      </div>
    </article>
  );
}

export function RunDetailDialog({
  run,
  jobs,
  loading,
  error,
  onOpenChange
}: {
  run: WorkflowBatchRun | null;
  jobs: JobDetail[];
  loading: boolean;
  error?: string;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  return (
    <Dialog
      open={Boolean(run)}
      title={run ? runTitle(run) : "Run detail"}
      description={run ? `${sourceLabel(run.source)} · ${run.status} · ${formatDate(run.created_at)}` : undefined}
      className="flex h-[88vh] max-w-5xl flex-col overflow-hidden"
      bodyClassName="min-h-0 flex-1 overflow-y-auto pr-1"
      onOpenChange={onOpenChange}
    >
      {!run ? null : (
        <div className="space-y-4">
          <dl className="grid gap-3 text-sm sm:grid-cols-4">
            <Detail label="Source" value={sourceLabel(run.source)} />
            <Detail label="Schedule" value={run.schedule_id ? String(run.schedule_id) : "-"} />
            <Detail label="Created" value={formatDate(run.created_at)} />
            <Detail label="Finished" value={formatDate(run.finished_at)} />
          </dl>
          <section className="rounded-md border bg-muted/20 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <WorkflowRunStatusPill status={run.status} />
              <Badge tone="muted">{run.completed}/{run.total} completed</Badge>
              <Badge tone={run.failed ? "danger" : "muted"}>{run.failed} failed</Badge>
              <Badge tone={run.skipped ? "warning" : "muted"}>{run.skipped} skipped</Badge>
            </div>
          </section>
          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Items</h3>
            {run.items.map((item) => (
              <div key={item.id ?? item.draft_id} className="rounded-md border bg-card p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{item.title}</span>
                  <Badge tone={workflowItemTone(item.status)}>{item.status}</Badge>
                </div>
                <dl className="mt-3 grid gap-3 sm:grid-cols-3">
                  <Detail label="Draft" value={item.draft_id} />
                  <Detail label="Jobs" value={item.job_ids.length ? item.job_ids.join(", ") : "-"} />
                  <Detail label="Finished" value={formatDate(item.finished_at)} />
                </dl>
                {item.error_message ? (
                  <p className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                    {item.error_message}
                  </p>
                ) : null}
              </div>
            ))}
          </section>
          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Jobs</h3>
            {loading ? (
              <DataState title="Loading jobs" variant="loading" />
            ) : error ? (
              <DataState title="Could not load jobs" description={error} variant="error" />
            ) : jobs.length === 0 ? (
              <p className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">No jobs were created.</p>
            ) : (
              jobs.map((job) => <RunJobDetail key={job.id} job={job} />)
            )}
          </section>
        </div>
      )}
    </Dialog>
  );
}

export function RunJobDetail({ job }: { job: JobDetail }): JSX.Element {
  const latestEvent = job.events.at(-1);
  return (
    <article className="rounded-md border bg-card p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="break-words text-sm font-semibold">{jobLabel(job)}</h4>
            <Badge tone={jobStatusTone(job.status)}>{job.status}</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{jobTarget(job)}</p>
        </div>
        <p className="text-sm text-muted-foreground">{job.completed_files}/{job.total_files || 0} files</p>
      </div>
      {job.error_message ? (
        <p className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          {job.error_message}
        </p>
      ) : null}
      <div className="mt-3">
        {latestEvent ? (
          <div className="rounded-md border bg-muted/20 p-2 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Badge tone={latestEvent.level === "error" ? "danger" : latestEvent.level === "warning" ? "warning" : "muted"}>
                {latestEvent.level}
              </Badge>
              <span className="text-muted-foreground">{formatDate(latestEvent.created_at)}</span>
            </div>
            <p className="mt-1 break-words">{latestEvent.message}</p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No events recorded.</p>
        )}
      </div>
    </article>
  );
}

export function ScheduleWorkflowCard({
  task,
  lastRun,
  onRuntimeChanged
}: {
  task: ScheduledTask;
  lastRun: WorkflowBatchRun | null;
  onRuntimeChanged?: () => void;
}): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    void queryClient.invalidateQueries({ queryKey: ["scheduled-tasks"] });
    void queryClient.invalidateQueries({ queryKey: ["workflow-runs"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    onRuntimeChanged?.();
  };
  const runMutation = useMutation({
    mutationFn: () => runScheduledTask(task.id),
    onSuccess: (response) => {
      pushToast({
        title: response.workflow_run_id
          ? "Schedule run submitted"
          : response.skipped
            ? "Schedule skipped"
            : "Schedule checked",
        description: response.workflow_run_id ?? (response.job_ids.length ? response.job_ids.join(", ") : undefined),
        tone: response.skipped ? "info" : "success"
      });
      invalidate();
    },
    onError: (error) => pushToast({ title: "Schedule could not run", description: error.message, tone: "error" })
  });
  const statusMutation = useMutation({
    mutationFn: (status: ScheduledTask["status"]) => updateScheduledTask(task.id, { status }),
    onSuccess: (_response, status) => {
      pushToast({
        title:
          status === "archived"
            ? "Schedule archived"
            : status === "active"
              ? "Schedule activation requested"
              : "Schedule paused",
        tone: "success"
      });
      invalidate();
    },
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
  const busy = runMutation.isPending || statusMutation.isPending || deleteMutation.isPending;

  return (
    <article className="surface p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-sm font-semibold">{task.name}</h2>
            <Badge tone={task.status === "active" ? "success" : task.status === "blocked" ? "danger" : "muted"}>
              {task.status}
            </Badge>
            <Badge tone="default">schedule</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{scheduleSummary(task)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => runMutation.mutate()}>
            <Play className="h-4 w-4" aria-hidden="true" />
            Run
          </Button>
          {task.status === "active" ? (
            <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => statusMutation.mutate("paused")}>
              <Pause className="h-4 w-4" aria-hidden="true" />
              Pause
            </Button>
          ) : (
            <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => statusMutation.mutate("active")}>
              <Play className="h-4 w-4" aria-hidden="true" />
              Activate
            </Button>
          )}
          {task.status === "archived" ? null : (
            <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => statusMutation.mutate("archived")}>
              Archive
            </Button>
          )}
          <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => deleteMutation.mutate()}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            Delete
          </Button>
        </div>
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <Detail label="Next run" value={formatDate(task.next_run_at)} />
        <Detail label="Last run" value={formatDate(task.last_run_at)} />
        <Detail label="Latest run" value={lastRunLabel(task, lastRun)} />
      </dl>
      {task.last_error_message ? (
        <p className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          {task.last_error_message}
        </p>
      ) : null}
    </article>
  );
}

export function WorkflowLimitPanel({
  jobs,
  settings,
  disabled,
  onSync
}: {
  jobs: Job[];
  settings?: SettingsResponse;
  disabled: boolean;
  onSync: (key: "max_active_one_time_tasks", value: number) => void;
}): JSX.Element {
  const runStats = workflowJobStats(jobs);

  return (
    <div className="min-w-0">
      <WorkflowLimitControl
        label="Run limit"
        value={settings?.max_active_one_time_tasks ?? 1}
        disabled={disabled || !settings}
        active={runStats.active}
        waiting={runStats.waiting}
        onSync={(value) => onSync("max_active_one_time_tasks", value)}
      />
    </div>
  );
}

function WorkflowLimitControl({
  label,
  value,
  disabled,
  active,
  waiting,
  onSync
}: {
  label: string;
  value: number;
  disabled: boolean;
  active: number;
  waiting: number;
  onSync: (value: number) => void;
}): JSX.Element {
  const initialCustomValue = value >= 6 ? value : 6;
  const [draftValue, setDraftValue] = React.useState(String(initialCustomValue));
  const [customValue, setCustomValue] = React.useState(initialCustomValue);
  const [editingCustom, setEditingCustom] = React.useState(value < 6);

  React.useEffect(() => {
    if (value >= 6) {
      setCustomValue(value);
      setDraftValue(String(value));
      setEditingCustom(false);
    }
  }, [value]);

  const parsedCustomValue = clampCustomLimit(Number(draftValue));
  const customActive = value === customValue;
  const customChanged = customValue !== value;

  function normalizeCustomEdit() {
    setCustomValue(parsedCustomValue);
    setDraftValue(String(parsedCustomValue));
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="whitespace-nowrap text-xs font-medium">{label}</span>
      <span className="whitespace-nowrap text-xs text-muted-foreground">
        {active}/{waiting}
      </span>
      <div className="flex flex-wrap items-center gap-1">
        {[1, 2, 3, 4, 5].map((item) => (
          <Button
            key={item}
            type="button"
            size="icon"
            variant={value === item ? "default" : "outline"}
            className="h-7 w-7 shrink-0 text-xs"
            disabled={disabled}
            title={`Set ${label} limit to ${item}`}
            onClick={() => {
              setDraftValue(String(item));
              onSync(item);
            }}
          >
            {item}
          </Button>
        ))}
        {editingCustom ? (
          <Input
            type="number"
            min={6}
            value={draftValue}
            disabled={disabled}
            className="h-7 w-14 px-2 text-center text-xs"
            title={`Custom ${label} limit, minimum 6`}
            onChange={(event) => setDraftValue(event.target.value)}
            onBlur={normalizeCustomEdit}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
              }
            }}
          />
        ) : (
          <Button
            type="button"
            size="sm"
            variant={customActive ? "default" : "outline"}
            className="h-7 min-w-10 shrink-0 px-2 text-xs"
            disabled={disabled}
            title={`Edit custom ${label} limit`}
            onClick={() => setEditingCustom(true)}
          >
            {customValue}
          </Button>
        )}
        <Button
          type="button"
          size="icon"
          variant={customChanged ? "default" : "outline"}
          className="h-7 w-7 shrink-0"
          disabled={disabled}
          title={`Sync ${label} limit`}
          onClick={() => {
            if (editingCustom) {
              onSync(parsedCustomValue);
              setCustomValue(parsedCustomValue);
              setDraftValue(String(parsedCustomValue));
              setEditingCustom(false);
              return;
            }
            onSync(customValue);
          }}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

function WorkflowRunStatusPill({ status }: { status: WorkflowBatchRun["status"] }): JSX.Element {
  return <Badge tone={workflowRunTone(status)}>{status}</Badge>;
}

export function Detail({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <dt className="text-xs uppercase text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words font-medium">{value}</dd>
    </div>
  );
}

function clampCustomLimit(value: number): number {
  if (!Number.isFinite(value)) {
    return 6;
  }
  return Math.max(6, Math.floor(value));
}

export function loadRunJobs(run: WorkflowBatchRun | null): Promise<JobDetail[]> {
  if (!run) {
    return Promise.resolve([]);
  }
  const ids = Array.from(new Set(run.items.flatMap((item) => item.job_ids)));
  return Promise.all(ids.map((jobId) => getJob(jobId)));
}
