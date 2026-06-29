import type { Job } from "@/api/jobs";
import type { ScheduledTask } from "@/api/scheduledTasks";
import type { WorkflowBatchRun, WorkflowBatchRunItem } from "@/api/workflows";

export type WorkflowRunGroups = {
  active: WorkflowBatchRun[];
  failed: WorkflowBatchRun[];
  completed: WorkflowBatchRun[];
};

export type WorkflowScheduleGroups = {
  active: ScheduledTask[];
  blocked: ScheduledTask[];
  inactive: ScheduledTask[];
  archived: ScheduledTask[];
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

export function workflowRunGroups(runs: WorkflowBatchRun[]): WorkflowRunGroups {
  return {
    active: runs.filter((run) => run.status === "running"),
    failed: runs.filter((run) => run.status === "failed" || run.status === "partial"),
    completed: runs.filter((run) => run.status === "completed" || run.status === "skipped")
  };
}

export function emptyRunGroups(): WorkflowRunGroups {
  return { active: [], failed: [], completed: [] };
}

export function workflowScheduleGroups(tasks: ScheduledTask[]): WorkflowScheduleGroups {
  return {
    active: tasks.filter((task) => task.status === "active"),
    blocked: tasks.filter((task) => task.status === "blocked"),
    inactive: tasks.filter((task) => task.status === "paused" || task.status === "inactive"),
    archived: tasks.filter((task) => task.status === "archived")
  };
}

export function workflowWaitingJobs(jobs: Job[]): Job[] {
  return jobs.filter((job) => job.options.activation_scope === "one_time" && job.status === "inactive");
}

export function filterWorkflowRuns(runs: WorkflowBatchRun[], search: string): WorkflowBatchRun[] {
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
      run.items
        .flatMap((item) => [
          item.title,
          item.draft_id,
          item.status,
          item.failure_reason,
          item.error_message,
          item.job_ids.join(" ")
        ])
        .join(" ")
    ]).includes(query)
  );
}

export function filterSchedules(tasks: ScheduledTask[], search: string): ScheduledTask[] {
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
      scheduleSummary(task)
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

export function runJobIds(run: WorkflowBatchRun | null): string[] {
  if (!run) {
    return [];
  }
  return Array.from(new Set(run.items.flatMap((item) => item.job_ids)));
}

export function groupRunsByFailureReason(runs: WorkflowBatchRun[]): Array<{ reason: string; items: WorkflowBatchRun[] }> {
  return groupedByReason(runs, (run) => run.failure_reason || "unknown");
}

export function groupSchedulesByFailureReason(tasks: ScheduledTask[]): Array<{ reason: string; items: ScheduledTask[] }> {
  return groupedByReason(tasks, (task) => task.failure_reason || "unknown");
}

export function latestScheduleRun(task: ScheduledTask, runs: WorkflowBatchRun[]): WorkflowBatchRun | null {
  const summaryRunId = task.last_run_summary?.workflow_run_id;
  const matchedBySummary = typeof summaryRunId === "string" ? runs.find((run) => run.id === summaryRunId) : null;
  if (matchedBySummary) {
    return matchedBySummary;
  }
  return runs.find((run) => run.schedule_id === task.id) ?? null;
}

export function lastRunLabel(task: ScheduledTask, run: WorkflowBatchRun | null): string {
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
  const oneTimeJobs = jobs.filter((job) => job.options.activation_scope === "one_time");
  return {
    active: oneTimeJobs.filter((job) => job.status === "queued" || job.status === "running").length,
    waiting: oneTimeJobs.filter((job) => job.status === "inactive").length
  };
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
  if (source === "manual_schedule" || source === "schedule") {
    return "schedule";
  }
  if (source === "workflow_batch") {
    return "manual";
  }
  if (source.includes("shortcut")) {
    return "shortcut";
  }
  return source.replaceAll("_", " ");
}

export function runTitle(run: WorkflowBatchRun): string {
  if (run.items.length === 1) {
    return run.items[0].title;
  }
  return `${run.items.length} workflow item run`;
}

export function scheduleSummary(task: ScheduledTask): string {
  const target = targetLabels[task.config.target.type] ?? task.config.target.type;
  const actions = task.config.actions.map((action) => actionLabels[action] ?? action).join(" then ");
  return `${target} · ${actions} · every ${task.interval_days} days`;
}

export function workflowRunTone(status: WorkflowBatchRun["status"]): "default" | "success" | "danger" | "warning" | "muted" {
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

export function workflowItemTone(status: WorkflowBatchRunItem["status"]): "default" | "success" | "danger" | "warning" | "muted" {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed") {
    return "danger";
  }
  if (status === "running" || status === "pending") {
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
