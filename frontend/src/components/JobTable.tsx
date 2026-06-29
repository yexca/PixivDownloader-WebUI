import { Link } from "react-router-dom";
import { AlertCircle, Info, RefreshCw, RotateCcw, XCircle } from "lucide-react";

import type { Job } from "@/api/jobs";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ScrollableTable } from "@/components/ScrollableTable";
import { actionIconClass, cn, formatDate, isCancellable, isRerunnable, isRetryable, percent } from "@/lib/utils";

type JobTableProps = {
  jobs: Job[];
  onSelect?: (job: Job) => void;
  onSelectJobId?: (jobId: string) => void;
  onCancel?: (job: Job) => void;
  onRetry?: (job: Job) => void;
  onRerun?: (job: Job) => void;
  selectedJobId?: string | null;
  selectedIds?: Set<string>;
  busyRetryJobId?: string | null;
  busyRerunJobId?: string | null;
  onToggleSelected?: (jobId: string) => void;
  onToggleAllVisible?: () => void;
};

export function JobTable({
  jobs,
  onSelect,
  onSelectJobId,
  onCancel,
  onRetry,
  onRerun,
  selectedJobId,
  selectedIds,
  busyRetryJobId,
  busyRerunJobId,
  onToggleSelected,
  onToggleAllVisible
}: JobTableProps): JSX.Element {
  const sortedJobs = [...jobs].sort(compareJobsByCreatedDesc);
  const allVisibleSelected =
    sortedJobs.length > 0 && sortedJobs.every((job) => selectedIds?.has(job.id));

  return (
    <ScrollableTable>
      <table className="data-table min-w-[860px]">
        <thead className="table-head">
          <tr>
            {onToggleSelected ? (
              <th className="sticky-col-left w-10 px-3 py-2">
                <input
                  type="checkbox"
                  aria-label="Select all visible jobs"
                  checked={allVisibleSelected}
                  onChange={onToggleAllVisible}
                />
              </th>
            ) : null}
            <th className={onToggleSelected ? "sticky-col-left-offset px-3 py-2" : "sticky-col-left px-3 py-2"}>
              Job
            </th>
            <th className="px-3 py-2">Input</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Progress</th>
            <th className="px-3 py-2">Created</th>
            <th className="sticky-col-right px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {sortedJobs.map((job) => {
            const done = job.completed_files + job.skipped_files + job.failed_files;
            const selected = selectedJobId === job.id;
            return (
              <tr
                key={job.id}
                id={`job-${job.id}`}
                className={onSelect ? "cursor-pointer hover:bg-muted/40" : "hover:bg-muted/40"}
                data-selected={selected ? "true" : "false"}
                onClick={() => onSelect?.(job)}
              >
                {onToggleSelected ? (
                  <td className="table-cell sticky-col-left w-10">
                    <input
                      type="checkbox"
                      aria-label={`Select job ${job.id}`}
                      checked={selectedIds?.has(job.id) ?? false}
                      onClick={(event) => event.stopPropagation()}
                      onChange={() => onToggleSelected(job.id)}
                    />
                  </td>
                ) : null}
                <td className={onToggleSelected ? "table-cell sticky-col-left-offset min-w-64 max-w-80" : "table-cell sticky-col-left min-w-64 max-w-80"}>
                  <div className="font-medium">{job.type.replaceAll("_", " ")}</div>
                  <div className="break-all text-xs text-muted-foreground">{job.id}</div>
                  <JobLineage job={job} onSelectJobId={onSelectJobId} />
                </td>
                <td className="table-cell">
                  {job.input_user_id ? (
                    <Link
                      className="text-primary hover:underline"
                      to={`/artists/${job.input_user_id}`}
                      onClick={(event) => event.stopPropagation()}
                    >
                      User {job.input_user_id}
                    </Link>
                  ) : (
                    `Artwork ${job.input_artwork_id ?? "-"}`
                  )}
                </td>
                <td className="table-cell">
                  <StatusBadge status={job.status} />
                </td>
                <td className="table-cell w-52">
                  <Progress value={percent(done, job.total_files)} />
                  <div className="mt-1 text-xs text-muted-foreground">
                    {done}/{job.total_files || "-"}
                  </div>
                </td>
                <td className="table-cell">{formatDate(job.created_at)}</td>
                <td className="table-cell sticky-col-right min-w-36 cursor-default" onClick={(event) => event.stopPropagation()}>
                  <div className="flex items-center gap-1">
                    {onRetry && isRetryable(job.status) ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        className={actionIconClass("warning")}
                        title={retryTitle(job)}
                        aria-label={retryTitle(job)}
                        disabled={busyRetryJobId === job.id || Boolean(activeRelatedJob(job, "retry"))}
                        onClick={(event) => {
                          event.stopPropagation();
                          onRetry(job);
                        }}
                      >
                        <RetryFailedIcon spinning={busyRetryJobId === job.id} />
                      </Button>
                    ) : null}
                    {onRerun && isRerunnable(job.status) ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        className={actionIconClass()}
                        title={rerunTitle(job)}
                        aria-label={rerunTitle(job)}
                        disabled={busyRerunJobId === job.id || Boolean(activeRelatedJob(job, "rerun"))}
                        onClick={(event) => {
                          event.stopPropagation();
                          onRerun(job);
                        }}
                      >
                        <RefreshCw className={busyRerunJobId === job.id ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden="true" />
                      </Button>
                    ) : null}
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className={actionIconClass(selected ? "selected" : "default")}
                      title="Show job details"
                      aria-label="Show job details"
                      onClick={(event) => {
                        event.stopPropagation();
                        onSelect?.(job);
                      }}
                    >
                      <Info className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    {onCancel && isCancellable(job.status) ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        className={actionIconClass("danger")}
                        title={job.status === "running" ? "Request job cancellation" : "Cancel job"}
                        aria-label={job.status === "running" ? "Request job cancellation" : "Cancel job"}
                        disabled={job.cancel_requested}
                        onClick={(event) => {
                          event.stopPropagation();
                          onCancel(job);
                        }}
                      >
                        <XCircle className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    ) : null}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </ScrollableTable>
  );
}

function compareJobsByCreatedDesc(left: Job, right: Job): number {
  return timestamp(right.created_at) - timestamp(left.created_at);
}

function timestamp(value: string | null): number {
  return value ? Date.parse(value) || 0 : 0;
}

function JobLineage({ job, onSelectJobId }: { job: Job; onSelectJobId?: (jobId: string) => void }): JSX.Element | null {
  const sourceJobId = job.options.source_job_id;
  const action = job.options.job_action;
  const latestRelated = latestRelatedJob(job);
  if ((typeof sourceJobId !== "string" || !sourceJobId) && !latestRelated) {
    return null;
  }
  if (latestRelated) {
    return (
      <div className="mt-1 text-xs text-muted-foreground">
        {jobActionPastLabel(latestRelated.action)} by{" "}
        <button
          type="button"
          className="font-medium text-primary hover:underline"
          onClick={(event) => {
            event.stopPropagation();
            onSelectJobId?.(latestRelated.id);
          }}
        >
          {shortJobId(latestRelated.id)}
        </button>
      </div>
    );
  }
  return (
    <div className="mt-1 text-xs text-muted-foreground">
      {typeof sourceJobId === "string" && sourceJobId
        ? `${jobActionLabel(action)} of ${shortJobId(sourceJobId)}`
        : null}
    </div>
  );
}

function jobActionLabel(action: unknown): string {
  if (action === "rerun") {
    return "Rerun";
  }
  if (action === "retry_failed_artists") {
    return "Retry failed artists";
  }
  return "Retry";
}

function jobActionPastLabel(action: unknown): string {
  if (action === "rerun") {
    return "Reran";
  }
  if (action === "retry_failed_artists") {
    return "Retry failed artists";
  }
  return "Retried";
}

function shortJobId(jobId: string): string {
  return jobId.slice(0, 8);
}

function activeRelatedJob(job: Job, action: "retry" | "rerun"): Job["related_jobs"][number] | undefined {
  return job.related_jobs.find((related) => {
    const relatedAction = normalizeAction(related.action);
    return relatedAction === action && ["inactive", "queued", "running"].includes(related.status);
  });
}

function latestRelatedJob(job: Job): Job["related_jobs"][number] | undefined {
  return [...job.related_jobs].sort((left, right) => timestamp(right.created_at) - timestamp(left.created_at))[0];
}

function normalizeAction(action: unknown): "retry" | "rerun" {
  return action === "rerun" ? "rerun" : "retry";
}

function retryTitle(job: Job): string {
  const active = activeRelatedJob(job, "retry");
  if (active) {
    return `Retry already queued as ${shortJobId(active.id)}`;
  }
  return job.type === "hydrate_legacy_import" ? "Retry failed artists" : "Retry failed";
}

function rerunTitle(job: Job): string {
  const active = activeRelatedJob(job, "rerun");
  return active ? `Rerun already queued as ${shortJobId(active.id)}` : "Rerun job";
}

function RetryFailedIcon({ spinning }: { spinning: boolean }): JSX.Element {
  return (
    <span className="relative inline-flex h-4 w-4 items-center justify-center" aria-hidden="true">
      <RotateCcw className={cn("h-4 w-4", spinning && "animate-spin")} />
      <AlertCircle className="absolute -right-1 -top-1 h-2.5 w-2.5 fill-background text-[hsl(var(--warning))]" />
    </span>
  );
}
