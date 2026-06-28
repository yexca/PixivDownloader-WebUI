import { Link } from "react-router-dom";
import { Info, RefreshCw, RotateCcw, XCircle } from "lucide-react";

import type { Job } from "@/api/jobs";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ScrollableTable } from "@/components/ScrollableTable";
import { formatDate, isCancellable, isRerunnable, isRetryable, percent } from "@/lib/utils";

type JobTableProps = {
  jobs: Job[];
  onSelect?: (job: Job) => void;
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
                <td className="table-cell sticky-col-right min-w-36">
                  <div className="flex items-center gap-1">
                    {onRetry && isRetryable(job.status) ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        title={job.type === "hydrate_legacy_import" ? "Retry failed artists" : "Retry job"}
                        aria-label={job.type === "hydrate_legacy_import" ? "Retry failed artists" : "Retry job"}
                        disabled={busyRetryJobId === job.id}
                        onClick={(event) => {
                          event.stopPropagation();
                          onRetry(job);
                        }}
                      >
                        <RotateCcw className={busyRetryJobId === job.id ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden="true" />
                      </Button>
                    ) : null}
                    {onRerun && isRerunnable(job.status) ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        title="Rerun job"
                        aria-label="Rerun job"
                        disabled={busyRerunJobId === job.id}
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
                      variant={selected ? "secondary" : "ghost"}
                      size="icon"
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
                        variant="ghost"
                        size="icon"
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
