import * as React from "react";
import { AlertCircle, CheckCircle2, Clock3, Pause, Play, RefreshCw, Trash2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { getJob, type Job, type JobDetail } from "@/api/jobs";
import {
  deleteScheduledTask,
  runScheduledTask,
  type ScheduledTask,
  updateScheduledTask
} from "@/api/scheduledTasks";
import type { SettingsResponse } from "@/api/settings";
import type { WorkflowBatchRun, WorkflowNodeRun } from "@/api/workflows";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs } from "@/components/ui/tabs";
import { DataState } from "@/components/DataState";
import { useToast } from "@/components/ToastProvider";
import { cn, formatDate } from "@/lib/utils";
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
        {(run.node_runs.length ? run.node_runs : run.items).map((item) => (
          <div key={item.id ?? item.title} className="rounded-md border bg-muted/20 p-3 text-sm">
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
  const [selectedNodeId, setSelectedNodeId] = React.useState<string | null>(null);
  const [detailTab, setDetailTab] = React.useState<NodeDetailTab>("summary");

  React.useEffect(() => {
    setSelectedNodeId(run?.node_runs[0]?.node_id ?? null);
    setDetailTab("summary");
  }, [run?.id, run?.node_runs]);

  const selectedNode =
    run?.node_runs.find((node) => node.node_id === selectedNodeId) ?? run?.node_runs[0] ?? null;
  const selectedNodeJobs = selectedNode ? jobs.filter((job) => selectedNode.job_ids.includes(job.id)) : [];

  return (
    <Dialog
      open={Boolean(run)}
      title={run ? runTitle(run) : "Run detail"}
      description={run ? `${sourceLabel(run.source)} · ${run.status} · ${formatDate(run.created_at)}` : undefined}
      className="flex h-[90vh] max-w-6xl flex-col overflow-hidden"
      bodyClassName="min-h-0 flex-1 overflow-hidden"
      onOpenChange={onOpenChange}
    >
      {!run ? null : (
        <div className="flex h-full min-h-0 flex-col gap-4">
          <RunDetailHeader run={run} />
          {run.node_runs.length ? (
            <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[290px_minmax(0,1fr)]">
              <NodeTimeline nodes={run.node_runs} selectedNodeId={selectedNode?.node_id ?? null} onSelect={setSelectedNodeId} />
              <section className="min-h-0 overflow-y-auto pr-1">
                {selectedNode ? (
                  <NodeDetailPanel
                    node={selectedNode}
                    jobs={selectedNodeJobs}
                    loading={loading}
                    error={error}
                    tab={detailTab}
                    onTabChange={setDetailTab}
                  />
                ) : (
                  <DataState title="No node selected" description="Select a workflow node to inspect its runtime data." />
                )}
              </section>
            </div>
          ) : (
            <LegacyRunDetail run={run} jobs={jobs} loading={loading} error={error} />
          )}
        </div>
      )}
    </Dialog>
  );
}

export function RunJobDetail({ job }: { job: JobDetail }): JSX.Element {
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const sortedEvents = [...job.events].sort((left, right) => timeValue(right.created_at) - timeValue(left.created_at));
  const latestEvent = sortedEvents[0];
  const olderEvents = sortedEvents.slice(1);
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
          <JobEventCard event={latestEvent} label="Latest" />
        ) : (
          <p className="text-sm text-muted-foreground">No events recorded.</p>
        )}
        {olderEvents.length ? (
          <div className="mt-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => setHistoryOpen((open) => !open)}>
              {historyOpen ? "Hide" : "Show"} {olderEvents.length} older event(s)
            </Button>
            {historyOpen ? (
              <div className="mt-2 space-y-2">
                {olderEvents.map((event) => (
                  <JobEventCard key={event.id ?? `${event.created_at}-${event.message}`} event={event} />
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

type NodeDetailTab = "summary" | "data" | "jobs";

const nodeDetailTabs: Array<{ value: NodeDetailTab; label: string }> = [
  { value: "summary", label: "Summary" },
  { value: "data", label: "Data" },
  { value: "jobs", label: "Jobs" }
];

function RunDetailHeader({ run }: { run: WorkflowBatchRun }): JSX.Element {
  return (
    <section className="rounded-md border bg-muted/20 p-3">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <WorkflowRunStatusPill status={run.status} />
            <Badge tone="muted">{sourceLabel(run.source)}</Badge>
            <Badge tone="muted">Concurrency {run.concurrency}</Badge>
          </div>
          <p className="mt-2 break-all text-xs text-muted-foreground">{run.id}</p>
        </div>
        <div className="grid gap-3 text-sm sm:grid-cols-4 xl:min-w-[560px]">
          <Detail label="Completed" value={`${run.completed}/${run.total}`} />
          <Detail label="Failed" value={String(run.failed)} />
          <Detail label="Created" value={formatDate(run.created_at)} />
          <Detail label="Finished" value={formatDate(run.finished_at)} />
        </div>
      </div>
    </section>
  );
}

function NodeTimeline({
  nodes,
  selectedNodeId,
  onSelect
}: {
  nodes: WorkflowNodeRun[];
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
}): JSX.Element {
  return (
    <aside className="min-h-0 overflow-y-auto rounded-md border bg-muted/10 p-3">
      <h3 className="px-1 text-sm font-semibold">Node Timeline</h3>
      <div className="mt-3 space-y-2">
        {nodes.map((node) => {
          const selected = selectedNodeId === node.node_id;
          const Icon = nodeStatusIcon(node.status);
          return (
            <button
              key={node.id ?? node.node_id}
              type="button"
              className={cn(
                "flex w-full gap-3 rounded-md border bg-background p-3 text-left text-sm transition-colors hover:bg-muted/50",
                selected && "border-primary bg-primary/5"
              )}
              onClick={() => onSelect(node.node_id)}
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-muted text-xs font-semibold">
                <Icon className={cn("h-4 w-4", node.status === "running" && "animate-spin text-primary")} aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">{node.title}</span>
                  <Badge tone={workflowItemTone(node.status)}>{node.status}</Badge>
                </span>
                <span className="mt-1 block text-xs text-muted-foreground">
                  {node.position + 1}. {node.node_type} · {node.job_ids.length} job(s)
                </span>
                {node.error_message ? <span className="mt-1 block truncate text-xs text-destructive">{node.error_message}</span> : null}
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}

function NodeDetailPanel({
  node,
  jobs,
  loading,
  error,
  tab,
  onTabChange
}: {
  node: WorkflowNodeRun;
  jobs: JobDetail[];
  loading: boolean;
  error?: string;
  tab: NodeDetailTab;
  onTabChange: (tab: NodeDetailTab) => void;
}): JSX.Element {
  return (
    <div className="space-y-4">
      <section className="rounded-md border bg-card p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="break-words text-base font-semibold">{node.title}</h3>
              <Badge tone={workflowItemTone(node.status)}>{node.status}</Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {node.position + 1}. {node.node_type} · {node.node_id}
            </p>
          </div>
          <Tabs value={tab} onValueChange={onTabChange} items={nodeDetailTabs} />
        </div>
        {node.error_message ? (
          <p className="mt-4 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
            {node.error_message}
          </p>
        ) : null}
      </section>

      {tab === "summary" ? <NodeSummary node={node} jobs={jobs} loading={loading} error={error} /> : null}
      {tab === "data" ? <NodeData node={node} /> : null}
      {tab === "jobs" ? <NodeJobs jobs={jobs} loading={loading} error={error} /> : null}
    </div>
  );
}

function NodeSummary({
  node,
  jobs,
  loading,
  error
}: {
  node: WorkflowNodeRun;
  jobs: JobDetail[];
  loading: boolean;
  error?: string;
}): JSX.Element {
  const completedFiles = jobs.reduce((total, job) => total + job.completed_files, 0);
  const failedFiles = jobs.reduce((total, job) => total + job.failed_files, 0);
  return (
    <section className="rounded-md border bg-card p-4">
      <div className="grid gap-3 text-sm sm:grid-cols-4">
        <Detail label="Started" value={formatDate(node.started_at)} />
        <Detail label="Finished" value={formatDate(node.finished_at)} />
        <Detail label="Jobs" value={String(node.job_ids.length)} />
        <Detail label="Files" value={loading ? "Loading" : error ? "-" : `${completedFiles} ok / ${failedFiles} failed`} />
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <SummaryJson title="Config" value={node.input.config} />
        <SummaryJson title="Output" value={node.output} />
      </div>
    </section>
  );
}

function NodeData({ node }: { node: WorkflowNodeRun }): JSX.Element {
  return (
    <section className="grid gap-3 lg:grid-cols-2">
      <JsonBlock title="Input" value={node.input} />
      <JsonBlock title="Output" value={node.output} />
    </section>
  );
}

function NodeJobs({
  jobs,
  loading,
  error
}: {
  jobs: JobDetail[];
  loading: boolean;
  error?: string;
}): JSX.Element {
  if (loading) {
    return <DataState title="Loading jobs" variant="loading" />;
  }
  if (error) {
    return <DataState title="Could not load jobs" description={error} variant="error" />;
  }
  if (!jobs.length) {
    return <p className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">No jobs were linked to this node.</p>;
  }
  return (
    <section className="space-y-3">
      {jobs.map((job) => (
        <RunJobDetail key={job.id} job={job} />
      ))}
    </section>
  );
}

function LegacyRunDetail({
  run,
  jobs,
  loading,
  error
}: {
  run: WorkflowBatchRun;
  jobs: JobDetail[];
  loading: boolean;
  error?: string;
}): JSX.Element {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto pr-1">
      <div className="space-y-4">
        <RunDetailHeader run={run} />
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
    </div>
  );
}

function SummaryJson({ title, value }: { title: string; value: unknown }): JSX.Element {
  const summary = summarizeObject(value);
  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <p className="text-xs font-medium uppercase text-muted-foreground">{title}</p>
      {summary.length ? (
        <dl className="mt-2 space-y-2 text-sm">
          {summary.map(([key, item]) => (
            <div key={key} className="grid gap-1">
              <dt className="text-xs text-muted-foreground">{key}</dt>
              <dd className="break-words font-medium">{item}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">No data</p>
      )}
    </div>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }): JSX.Element {
  return (
    <section className="rounded-md border bg-card p-3">
      <h4 className="text-sm font-semibold">{title}</h4>
      <pre className="mt-3 max-h-[520px] overflow-auto rounded-md border bg-muted/30 p-3 text-xs leading-relaxed">
        {JSON.stringify(value ?? {}, null, 2)}
      </pre>
    </section>
  );
}

function JobEventCard({ event, label }: { event: JobDetail["events"][number]; label?: string }): JSX.Element {
  return (
    <div className="rounded-md border bg-muted/20 p-2 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {label ? <span className="font-medium">{label}</span> : null}
          <Badge tone={event.level === "error" ? "danger" : event.level === "warning" ? "warning" : "muted"}>
            {event.level}
          </Badge>
        </div>
        <span className="text-muted-foreground">{formatDate(event.created_at)}</span>
      </div>
      <p className="mt-1 break-words">{event.message}</p>
    </div>
  );
}

function nodeStatusIcon(status: WorkflowNodeRun["status"]): typeof Clock3 {
  if (status === "completed") {
    return CheckCircle2;
  }
  if (status === "failed") {
    return AlertCircle;
  }
  if (status === "running") {
    return RefreshCw;
  }
  return Clock3;
}

function summarizeObject(value: unknown): Array<[string, string]> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return [];
  }
  return Object.entries(value as Record<string, unknown>)
    .slice(0, 8)
    .map(([key, item]) => [key, summarizeValue(item)]);
}

function summarizeValue(value: unknown): string {
  if (Array.isArray(value)) {
    if (!value.length) {
      return "0 items";
    }
    return value.length <= 5 ? value.map((item) => String(item)).join(", ") : `${value.length} items`;
  }
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "object") {
    return `${Object.keys(value as Record<string, unknown>).length} field(s)`;
  }
  return String(value);
}

function timeValue(value: string | null): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
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
  onSync: (key: "max_active_run_jobs", value: number) => void;
}): JSX.Element {
  const runStats = workflowJobStats(jobs);

  return (
    <div className="min-w-0">
      <WorkflowLimitControl
        label="Run limit"
        value={settings?.max_active_run_jobs ?? 1}
        disabled={disabled || !settings}
        active={runStats.active}
        waiting={runStats.waiting}
        onSync={(value) => onSync("max_active_run_jobs", value)}
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
        {active}/{value}
      </span>
      {waiting ? <Badge tone="warning">{waiting} waiting</Badge> : null}
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
  const ids = Array.from(
    new Set([
      ...(run.node_runs.length
        ? run.node_runs.flatMap((node) => node.job_ids)
        : run.items.flatMap((item) => item.job_ids))
    ])
  );
  return Promise.all(ids.map((jobId) => getJob(jobId)));
}
