import type { Job } from "@/api/jobs";
import type { WorkflowTriggerRuntime } from "@/api/workflowTriggers";
import type { WorkflowRun } from "@/api/workflows";

export type WorkflowRunGroups = {
  active: WorkflowRun[];
  failed: WorkflowRun[];
  completed: WorkflowRun[];
};

export type WorkflowTriggerGroups = {
  active: WorkflowTriggerRuntime[];
  blocked: WorkflowTriggerRuntime[];
  inactive: WorkflowTriggerRuntime[];
  archived: WorkflowTriggerRuntime[];
};

const actionLabels: Record<string, string> = {
  download_artist: "Download",
  sync_artist: "Sync metadata",
  retry_failed_artist: "Retry failed files"
};

const targetLabels: Record<string, string> = {
  artists: "Artists",
  artworks: "Artworks",
  single_artist: "Single artist",
  single_artwork: "Single artwork",
  all_artists: "All artists",
  artists_with_tag: "Artists with tag",
  artists_not_checked: "Artists not checked"
};

export function workflowRunGroups(runs: WorkflowRun[]): WorkflowRunGroups {
  return {
    active: runs.filter((run) => run.status === "running"),
    failed: runs.filter((run) => run.status === "failed" || run.status === "partial"),
    completed: runs.filter((run) => run.status === "completed" || run.status === "skipped")
  };
}

export function emptyRunGroups(): WorkflowRunGroups {
  return { active: [], failed: [], completed: [] };
}

export function workflowTriggerGroups(tasks: WorkflowTriggerRuntime[]): WorkflowTriggerGroups {
  return {
    active: tasks.filter((task) => task.status === "active"),
    blocked: tasks.filter((task) => task.status === "blocked"),
    inactive: tasks.filter((task) => task.status === "paused" || task.status === "inactive"),
    archived: tasks.filter((task) => task.status === "archived")
  };
}

export function workflowWaitingJobs(jobs: Job[]): Job[] {
  return jobs.filter((job) => isWorkflowLimitedJob(job) && job.status === "inactive");
}

export function filterWorkflowRuns(runs: WorkflowRun[], search: string): WorkflowRun[] {
  const query = normalizeSearch(search);
  if (!query) {
    return runs;
  }
  return runs.filter((run) =>
    searchableText([
      run.id,
      run.status,
      run.source,
      run.failure_reason,
      run.node_runs
        .flatMap((node) => [
          node.title,
          node.node_id,
          node.node_type,
          node.status,
          node.failure_reason,
          node.error_message,
          node.job_ids.join(" ")
        ])
        .join(" "),
    ]).includes(query)
  );
}

export function filterWorkflowTriggers(tasks: WorkflowTriggerRuntime[], search: string): WorkflowTriggerRuntime[] {
  const query = normalizeSearch(search);
  if (!query) {
    return tasks;
  }
  return tasks.filter((task) =>
    searchableText([
      task.name,
      task.status,
      task.action,
      task.target_artist_id,
      task.failure_reason,
      task.last_error_code,
      task.last_error_message,
      workflowTriggerSummary(task)
    ]).includes(query)
  );
}

export function filterWaitingJobs(jobs: Job[], search: string): Job[] {
  const query = normalizeSearch(search);
  if (!query) {
    return jobs;
  }
  return jobs.filter((job) =>
    searchableText([
      job.id,
      job.status,
      job.type,
      job.workflow_source,
      job.input_user_id,
      job.input_artwork_id,
      job.error_message,
      jobTarget(job)
    ]).includes(query)
  );
}

export function runJobIds(run: WorkflowRun | null): string[] {
  if (!run) {
    return [];
  }
  const ids = run.node_runs.flatMap((node) => node.job_ids);
  return Array.from(new Set(ids));
}

export function groupRunsByFailureReason(runs: WorkflowRun[]): Array<{ reason: string; items: WorkflowRun[] }> {
  return groupedByReason(runs, (run) => run.failure_reason || "unknown");
}

export function groupWorkflowTriggersByFailureReason(tasks: WorkflowTriggerRuntime[]): Array<{ reason: string; items: WorkflowTriggerRuntime[] }> {
  return groupedByReason(tasks, (task) => task.failure_reason || "unknown");
}

export function latestWorkflowTriggerRun(task: WorkflowTriggerRuntime, runs: WorkflowRun[]): WorkflowRun | null {
  const summaryRunId = task.last_run_summary?.workflow_run_id;
  const matchedBySummary = typeof summaryRunId === "string" ? runs.find((run) => run.id === summaryRunId) : null;
  if (matchedBySummary) {
    return matchedBySummary;
  }
  return runs.find((run) => run.schedule_id === task.id) ?? null;
}

export function lastRunLabel(task: WorkflowTriggerRuntime, run: WorkflowRun | null): string {
  if (run) {
    return `${run.status} · ${run.completed}/${run.total}`;
  }
  const summaryRunId = task.last_run_summary?.workflow_run_id;
  if (typeof summaryRunId === "string") {
    return summaryRunId;
  }
  const count = task.last_run_summary?.created_jobs;
  return typeof count === "number" ? String(count) : task.last_job_id ?? "-";
}

export function workflowJobStats(jobs: Job[]): { active: number; waiting: number } {
  const oneTimeJobs = jobs.filter(isWorkflowLimitedJob);
  return {
    active: oneTimeJobs.filter((job) => job.status === "queued" || job.status === "running").length,
    waiting: oneTimeJobs.filter((job) => job.status === "inactive").length
  };
}

function isWorkflowLimitedJob(job: Job): boolean {
  return job.options.activation_scope === "one_time" || Boolean(job.workflow_run_id);
}

export function jobLabel(job: Job): string {
  return job.type.replaceAll("_", " ");
}

export function jobTarget(job: Job): string {
  if (job.input_user_id) {
    return `Artist ${job.input_user_id}`;
  }
  if (job.input_artwork_id) {
    return `Artwork ${job.input_artwork_id}`;
  }
  return "No target";
}

export function sourceLabel(source: string): string {
  if (source === "manual_workflow_trigger" || source === "workflow_trigger") {
    return "workflow trigger";
  }
  if (source === "manual_schedule" || source === "schedule") {
    return "workflow trigger";
  }
  if (source.includes("shortcut")) {
    return "shortcut";
  }
  return source.replaceAll("_", " ");
}

export function runTitle(run: WorkflowRun): string {
  if (run.name?.trim()) {
    return run.name;
  }
  if (run.definition_id) {
    return "Workflow run";
  }
  if (run.node_runs.length) {
    return run.node_runs[0]?.title || "Workflow run";
  }
  return "Workflow run";
}

export function workflowTriggerSummary(task: WorkflowTriggerRuntime): string {
  const target = targetLabels[task.config.target.type] ?? task.config.target.type;
  const actions = task.config.actions.map((action) => actionLabels[action] ?? action).join(" then ");
  return `${target} · ${actions} · every ${task.interval_days} days`;
}

export function workflowRunTone(status: WorkflowRun["status"]): "default" | "success" | "danger" | "warning" | "muted" {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed" || status === "partial") {
    return "danger";
  }
  if (status === "running") {
    return "default";
  }
  return "muted";
}

export function jobStatusTone(status: Job["status"]): "default" | "success" | "danger" | "warning" | "muted" {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed" || status === "cancelled") {
    return "danger";
  }
  if (status === "running" || status === "queued") {
    return "default";
  }
  return "muted";
}

function normalizeSearch(value: string): string {
  return value.trim().toLowerCase();
}

function searchableText(values: unknown[]): string {
  return values.filter(Boolean).join(" ").toLowerCase();
}

function groupedByReason<T>(items: T[], reasonFor: (item: T) => string): Array<{ reason: string; items: T[] }> {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const reason = reasonFor(item);
    groups.set(reason, [...(groups.get(reason) ?? []), item]);
  }
  return Array.from(groups.entries()).map(([reason, groupedItems]) => ({ reason, items: groupedItems }));
}
