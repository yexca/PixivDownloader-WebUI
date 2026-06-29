import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, CalendarClock, Pause, Play, RefreshCw, RotateCcw } from "lucide-react";

import {
  bulkCancelJobs,
  cancelJob,
  getJob,
  getJobQueueState,
  listJobs,
  pauseJobQueue,
  rerunJob,
  retryJob,
  resumeJobQueue,
  type Job,
  type JobActionResponse,
  type JobStatus
} from "@/api/jobs";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { DataState } from "@/components/DataState";
import { JobProgress } from "@/components/JobProgress";
import { JobTable } from "@/components/JobTable";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/Pagination";
import { useToast } from "@/components/ToastProvider";
import { cn, formatDate } from "@/lib/utils";

const statusOptions: Array<{ label: string; value: JobStatus | "" }> = [
  { label: "All statuses", value: "" },
  { label: "Queued", value: "queued" },
  { label: "Running", value: "running" },
  { label: "Completed", value: "completed" },
  { label: "Failed", value: "failed" },
  { label: "Cancelled", value: "cancelled" }
];

type CancelDialogState =
  | { kind: "single"; job: Job }
  | { kind: "bulk"; jobIds: string[]; label: string }
  | null;

export function JobsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const status = (searchParams.get("status") as JobStatus | null) ?? "";
  const page = Math.max(1, Number(searchParams.get("page") || "1"));
  const pageSize = Math.max(1, Number(searchParams.get("pageSize") || "50"));
  const [selectedJobId, setSelectedJobId] = React.useState<string | null>(
    searchParams.get("job")
  );
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(() => new Set());
  const [pendingRetryJobId, setPendingRetryJobId] = React.useState<string | null>(null);
  const [pendingRerunJobId, setPendingRerunJobId] = React.useState<string | null>(null);
  const [cancelDialog, setCancelDialog] = React.useState<CancelDialogState>(null);
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const jobs = useQuery({
    queryKey: ["jobs", status || "all", pageSize, page],
    queryFn: () => listJobs({ status, limit: pageSize, offset: (page - 1) * pageSize }),
    refetchInterval: status === "completed" || status === "failed" || status === "cancelled" ? false : 4000
  });
  const queueState = useQuery({
    queryKey: ["job-queue-state"],
    queryFn: getJobQueueState,
    refetchInterval: 4000
  });
  const selectedJob = useQuery({
    queryKey: ["job", selectedJobId],
    queryFn: () => getJob(selectedJobId!),
    enabled: Boolean(selectedJobId)
  });

  React.useEffect(() => {
    const jobId = searchParams.get("job");
    if (jobId && jobId !== selectedJobId) {
      setSelectedJobId(jobId);
    }
  }, [searchParams, selectedJobId]);

  const selectJob = (job: Job) => {
    setSelectedJobId(job.id);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("job", job.id);
    setSearchParams(nextParams, { replace: true });
  };
  const setParam = (key: string, value: string) => {
    const nextParams = new URLSearchParams(searchParams);
    if (value) {
      nextParams.set(key, value);
    } else {
      nextParams.delete(key);
    }
    nextParams.set("page", "1");
    setSearchParams(nextParams, { replace: true });
  };
  const setPageParam = (nextPage: number) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("page", String(nextPage));
    setSearchParams(nextParams, { replace: true });
  };
  const setPageSizeParam = (nextPageSize: number) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("pageSize", String(nextPageSize));
    nextParams.set("page", "1");
    setSearchParams(nextParams, { replace: true });
  };
  const toggleSelected = (jobId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(jobId)) {
        next.delete(jobId);
      } else {
        next.add(jobId);
      }
      return next;
    });
  };
  const toggleAllVisible = () => {
    const visibleIds = jobs.data?.items.map((job) => job.id) ?? [];
    setSelectedIds((current) => {
      const next = new Set(current);
      const allSelected = visibleIds.length > 0 && visibleIds.every((id) => next.has(id));
      visibleIds.forEach((id) => {
        if (allSelected) {
          next.delete(id);
        } else {
          next.add(id);
        }
      });
      return next;
    });
  };
  const cancelOne = useMutation({
    mutationFn: (job: Job) => cancelJob(job.id),
    onSuccess: () => {
      setCancelDialog(null);
      pushToast({ title: "Cancellation requested", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["job"] });
    },
    onError: (error) => pushToast({ title: "Cancel failed", description: error.message, tone: "error" })
  });
  const bulkCancel = useMutation({
    mutationFn: (jobIds: string[]) => bulkCancelJobs(jobIds),
    onSuccess: (response) => {
      setCancelDialog(null);
      setSelectedIds(new Set());
      pushToast({
        title: "Bulk cancel finished",
        description: `${response.cancelled.length} cancelled, ${response.errors.length} skipped.`,
        tone: response.errors.length ? "info" : "success"
      });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["job"] });
    },
    onError: (error) => pushToast({ title: "Bulk cancel failed", description: error.message, tone: "error" })
  });
  const pauseQueue = useMutation({
    mutationFn: pauseJobQueue,
    onSuccess: () => {
      pushToast({ title: "Queue paused", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["job-queue-state"] });
    },
    onError: (error) => pushToast({ title: "Pause failed", description: error.message, tone: "error" })
  });
  const resumeQueue = useMutation({
    mutationFn: resumeJobQueue,
    onSuccess: () => {
      pushToast({ title: "Queue resumed", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["job-queue-state"] });
    },
    onError: (error) => pushToast({ title: "Resume failed", description: error.message, tone: "error" })
  });
  const selectedCount = selectedIds.size;
  const queuedJobIds = jobs.data?.items.filter((job) => job.status === "queued").map((job) => job.id) ?? [];
  const selectJobId = (jobId: string) => {
    setSelectedJobId(jobId);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("job", jobId);
    setSearchParams(nextParams, { replace: true });
  };
  const onActionSuccess = (response: JobActionResponse) => {
    const title = response.action === "rerun" ? "Job queued again" : "Retry failed queued";
    pushToast({ title, description: response.job_id, tone: "success" });
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    void queryClient.invalidateQueries({ queryKey: ["job"] });
    selectJobId(response.job_id);
  };
  const retryOne = useMutation({
    mutationFn: (job: Job) => retryJob(job.id),
    onSuccess: onActionSuccess,
    onError: (error) => pushToast({ title: "Retry failed", description: error.message, tone: "error" }),
    onSettled: () => setPendingRetryJobId(null)
  });
  const rerunOne = useMutation({
    mutationFn: (job: Job) => rerunJob(job.id),
    onSuccess: onActionSuccess,
    onError: (error) => pushToast({ title: "Rerun failed", description: error.message, tone: "error" }),
    onSettled: () => setPendingRerunJobId(null)
  });
  const requestCancel = (job: Job) => {
    if (job.status === "running") {
      setCancelDialog({ kind: "single", job });
      return;
    }
    cancelOne.mutate(job);
  };
  const confirmCancel = () => {
    if (!cancelDialog) {
      return;
    }
    if (cancelDialog.kind === "single") {
      cancelOne.mutate(cancelDialog.job);
      return;
    }
    bulkCancel.mutate(cancelDialog.jobIds);
  };

  return (
    <>
      <PageHeader
        title="Jobs"
        description="Inspect queued, running, and completed download work."
        actions={
          <>
            <Select
              value={status}
              onChange={(event) => {
                setSelectedJobId(null);
                setParam("status", event.target.value);
              }}
              aria-label="Filter jobs by status"
            >
              {statusOptions.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
            <Button type="button" variant="outline" onClick={() => void jobs.refetch()} disabled={jobs.isFetching}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Refresh
            </Button>
            {queueState.data?.paused ? (
              <Button
                type="button"
                variant="outline"
                title="Resume the queue so queued jobs can start again."
                aria-label="Resume queue so queued jobs can start again"
                onClick={() => resumeQueue.mutate()}
                disabled={resumeQueue.isPending}
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                Resume Queue
              </Button>
            ) : (
              <Button
                type="button"
                variant="outline"
                title="Pause the queue. Running jobs continue; new queued jobs will not start."
                aria-label="Pause queue. Running jobs continue; new queued jobs will not start"
                onClick={() => pauseQueue.mutate()}
                disabled={pauseQueue.isPending}
              >
                <Pause className="h-4 w-4" aria-hidden="true" />
                Pause Queue
              </Button>
            )}
            <Button type="button" variant="outline" asChild>
              <Link to="/workflows">
                <CalendarClock className="h-4 w-4" aria-hidden="true" />
                Workflows
              </Link>
            </Button>
          </>
        }
      />
      <div className="grid gap-4 p-4 sm:p-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <section className="space-y-3">
          {queueState.data?.paused ? (
            <div className="status-warning rounded-md border px-3 py-2 text-sm">
              Queue paused. Running jobs will finish; no new queued jobs will start until the queue resumes.
            </div>
          ) : null}
          {selectedCount > 0 || queuedJobIds.length > 0 ? (
            <div className="flex flex-col gap-2 rounded-md border bg-card p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
              <div className="text-muted-foreground">
                {selectedCount > 0 ? `${selectedCount} selected` : `${queuedJobIds.length} queued on this page`}
              </div>
              <div className="flex flex-wrap gap-2">
                {selectedCount > 0 ? (
                  <>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={bulkCancel.isPending}
                      onClick={() => setCancelDialog({ kind: "bulk", jobIds: [...selectedIds], label: "selected jobs" })}
                    >
                      Cancel Selected
                    </Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
                      Clear
                    </Button>
                  </>
                ) : null}
                {queuedJobIds.length > 0 ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={bulkCancel.isPending}
                    onClick={() => setCancelDialog({ kind: "bulk", jobIds: queuedJobIds, label: "queued jobs on this page" })}
                  >
                    Cancel Queued
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}
          {jobs.isLoading ? (
            <DataState title="Loading jobs" variant="loading" />
          ) : jobs.isError ? (
            <DataState title="Could not load jobs" description={jobs.error.message} variant="error" />
          ) : jobs.data.items.length === 0 ? (
            <DataState title="No jobs found" description="Try another status filter or start a download." />
          ) : (
            <>
              <JobTable
                jobs={jobs.data.items}
                onSelect={selectJob}
                onSelectJobId={selectJobId}
                onCancel={requestCancel}
                onRetry={(job) => {
                  setPendingRetryJobId(job.id);
                  retryOne.mutate(job);
                }}
                onRerun={(job) => {
                  setPendingRerunJobId(job.id);
                  rerunOne.mutate(job);
                }}
                selectedJobId={selectedJobId}
                selectedIds={selectedIds}
                busyRetryJobId={pendingRetryJobId}
                busyRerunJobId={pendingRerunJobId}
                onToggleSelected={toggleSelected}
                onToggleAllVisible={toggleAllVisible}
              />
              <Pagination
                total={jobs.data.total}
                page={page}
                pageSize={pageSize}
                onPageChange={setPageParam}
                onPageSizeChange={setPageSizeParam}
              />
            </>
          )}
        </section>
        <aside className="space-y-3 xl:sticky xl:top-20 xl:self-start">
          {selectedJobId && selectedJob.data ? (
            <JobDetailPanel
              job={selectedJob.data}
              onSelectJob={selectJobId}
              onCancel={requestCancel}
              cancelPending={cancelOne.isPending}
            />
          ) : selectedJob.isLoading ? (
            <DataState title="Loading job detail" variant="loading" />
          ) : selectedJob.isError ? (
            <DataState title="Could not load job" description={selectedJob.error.message} variant="error" />
          ) : (
            <DataState title="Select a job" description="Job events and errors appear here." />
          )}
        </aside>
      </div>
      <CancelConfirmDialog
        state={cancelDialog}
        isPending={cancelOne.isPending || bulkCancel.isPending}
        onOpenChange={(open) => {
          if (!open) {
            setCancelDialog(null);
          }
        }}
        onConfirm={confirmCancel}
      />
    </>
  );
}

function JobDetailPanel({
  job,
  onSelectJob,
  onCancel,
  cancelPending
}: {
  job: Awaited<ReturnType<typeof getJob>>;
  onSelectJob: (jobId: string) => void;
  onCancel: (job: Job) => void;
  cancelPending: boolean;
}): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const onActionSuccess = (response: JobActionResponse) => {
    const title = response.action === "rerun" ? "Job queued again" : "Retry failed queued";
    pushToast({ title, description: response.job_id, tone: "success" });
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    void queryClient.invalidateQueries({ queryKey: ["job"] });
    onSelectJob(response.job_id);
  };
  const retryMutation = useMutation({
    mutationFn: () => retryJob(job.id),
    onSuccess: onActionSuccess,
    onError: (error) => pushToast({ title: "Retry failed", description: error.message, tone: "error" })
  });
  const rerunMutation = useMutation({
    mutationFn: () => rerunJob(job.id),
    onSuccess: onActionSuccess,
    onError: (error) => pushToast({ title: "Rerun failed", description: error.message, tone: "error" })
  });
  const canRetry = job.status === "failed";
  const canRerun = job.status === "completed" || job.status === "failed" || job.status === "cancelled";
  const activeRetry = activeRelatedJob(job, "retry");
  const activeRerun = activeRelatedJob(job, "rerun");

  return (
    <div className="surface flex flex-col p-4 xl:max-h-[calc(100vh-6.5rem)]">
      <div className="shrink-0">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Job Detail</h2>
            <p className="mt-1 break-all text-xs text-muted-foreground">{job.id}</p>
            <JobLineageNote job={job} onSelectJob={onSelectJob} />
          </div>
        </div>
        {job.status === "failed" ? <JobFailureSummary job={job} /> : null}
        <RelatedJobsNote job={job} onSelectJob={onSelectJob} />
        {canRetry || canRerun ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {canRetry ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="border-[hsl(var(--warning)/0.45)] text-[hsl(var(--warning))] hover:bg-[hsl(var(--warning-muted))]"
                title={activeRetry ? `Retry already queued as ${shortJobId(activeRetry.id)}` : "Retry only failed files or artists"}
                disabled={retryMutation.isPending || Boolean(activeRetry)}
                onClick={() => retryMutation.mutate()}
              >
                <RetryFailedIcon spinning={retryMutation.isPending} />
                {job.type === "hydrate_legacy_import" ? "Retry Failed Artists" : "Retry Failed"}
              </Button>
            ) : null}
            {canRerun ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                title={activeRerun ? `Rerun already queued as ${shortJobId(activeRerun.id)}` : "Create a new job with the same options"}
                disabled={rerunMutation.isPending || Boolean(activeRerun)}
                onClick={() => rerunMutation.mutate()}
              >
                <RefreshCw className={rerunMutation.isPending ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden="true" />
                Rerun
              </Button>
            ) : null}
          </div>
        ) : null}
        <div className="mt-4">
          <JobProgress job={job} cancelPending={cancelPending} onCancel={onCancel} />
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <Detail label="Created" value={formatDate(job.created_at)} />
          <Detail label="Started" value={formatDate(job.started_at)} />
          <Detail label="Finished" value={formatDate(job.finished_at)} />
          <Detail label="Artist" value={job.artist_id ?? "-"} />
        </dl>
        <h3 className="mt-5 text-sm font-semibold">Events</h3>
      </div>
      {job.events.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">No events recorded.</p>
      ) : (
        <div className="mt-3 min-h-0 flex-1 space-y-2 overflow-auto pr-1">
          {job.events.map((event) => (
            <div key={`${event.id}-${event.created_at}`} className="rounded-md border p-3 text-sm">
              <p>{event.message}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {event.level} · {formatDate(event.created_at)}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function JobFailureSummary({ job }: { job: Awaited<ReturnType<typeof getJob>> }): JSX.Element {
  const failedRetryableArtists = latestNumericPayload(job, "failed_retryable_artists");
  const reasonCounts = countFailureReasons(job);
  const primaryReason = reasonCounts[0]?.reason;
  const summary = failureSummaryText(job, primaryReason, failedRetryableArtists);

  return (
    <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
        <div className="min-w-0">
          <p className="font-medium text-destructive">{summary}</p>
          {job.error_message ? <p className="mt-1 break-words text-muted-foreground">{job.error_message}</p> : null}
          {reasonCounts.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
              {reasonCounts.slice(0, 3).map((item) => (
                <span key={item.reason} className="rounded-md border bg-background px-2 py-1">
                  {item.reason}: {item.count}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function CancelConfirmDialog({
  state,
  isPending,
  onOpenChange,
  onConfirm
}: {
  state: CancelDialogState;
  isPending: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}): JSX.Element {
  const isSingle = state?.kind === "single";
  const count = state?.kind === "bulk" ? state.jobIds.length : 1;
  const title = isSingle ? "Cancel running job?" : `Cancel ${count} ${state?.kind === "bulk" ? state.label : "job"}?`;
  const description = isSingle
    ? "This requests cancellation for the running job. The file in progress may be marked failed."
    : "This bulk action cannot be undone from the jobs page.";

  return (
    <Dialog
      open={Boolean(state)}
      title={title}
      description={description}
      onOpenChange={onOpenChange}
      footer={
        <>
          <Button type="button" variant="outline" disabled={isPending} onClick={() => onOpenChange(false)}>
            Keep Job
          </Button>
          <Button type="button" variant="destructive" disabled={isPending} onClick={onConfirm}>
            Confirm Cancel
          </Button>
        </>
      }
    />
  );
}

function JobLineageNote({
  job,
  onSelectJob
}: {
  job: Awaited<ReturnType<typeof getJob>>;
  onSelectJob: (jobId: string) => void;
}): JSX.Element | null {
  const sourceJobId = job.options.source_job_id;
  if (typeof sourceJobId !== "string" || !sourceJobId) {
    return null;
  }
  return (
    <p className="mt-1 text-xs text-muted-foreground">
      {jobLineageActionLabel(job.options.job_action)} of{" "}
      <button type="button" className="font-medium text-primary hover:underline" onClick={() => onSelectJob(sourceJobId)}>
        {sourceJobId}
      </button>
    </p>
  );
}

function RelatedJobsNote({
  job,
  onSelectJob
}: {
  job: Awaited<ReturnType<typeof getJob>>;
  onSelectJob: (jobId: string) => void;
}): JSX.Element | null {
  const active = job.related_jobs.filter((related) => ["inactive", "queued", "running"].includes(related.status));
  if (active.length === 0) {
    return null;
  }
  return (
    <div className="status-warning mt-3 rounded-md border p-3 text-sm">
      <p className="font-medium">Follow-up job already active</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {active.map((related) => (
          <button
            type="button"
            key={related.id}
            className="rounded-md border border-[hsl(var(--warning)/0.45)] bg-background px-2 py-1 text-xs font-medium text-[hsl(var(--warning-foreground))] hover:bg-[hsl(var(--warning-muted))]"
            onClick={() => onSelectJob(related.id)}
          >
            {jobLineageActionLabel(related.action)} {shortJobId(related.id)} · {related.status}
          </button>
        ))}
      </div>
    </div>
  );
}

function jobLineageActionLabel(action: unknown): string {
  if (action === "rerun") {
    return "Rerun";
  }
  if (action === "retry_failed_artists") {
    return "Retry failed artists";
  }
  return "Retry";
}

function failureSummaryText(job: Job, primaryReason: string | undefined, failedRetryableArtists: number | null): string {
  const failedArtists = failedRetryableArtists ?? job.failed_files;
  if (job.type === "hydrate_legacy_import") {
    if (primaryReason && /rate limit|restricted/i.test(primaryReason)) {
      return `Pixiv limited this metadata job. ${failedArtists || "Some"} artist(s) can be retried later.`;
    }
    return `${failedArtists || "Some"} legacy artist(s) failed and can be retried.`;
  }
  if (primaryReason) {
    return `Job failed: ${primaryReason}`;
  }
  return "Job failed. Review the events below for details.";
}

function latestNumericPayload(job: Awaited<ReturnType<typeof getJob>>, key: string): number | null {
  for (const event of [...job.events].reverse()) {
    const value = event.payload?.[key];
    if (typeof value === "number") {
      return value;
    }
  }
  return null;
}

function countFailureReasons(job: Awaited<ReturnType<typeof getJob>>): Array<{ reason: string; count: number }> {
  const counts = new Map<string, number>();
  for (const event of job.events) {
    if (event.level !== "error") {
      continue;
    }
    const reason = event.payload?.reason;
    if (typeof reason !== "string" || !reason.trim()) {
      continue;
    }
    counts.set(reason, (counts.get(reason) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((left, right) => right.count - left.count);
}

function activeRelatedJob(job: Job, action: "retry" | "rerun"): Job["related_jobs"][number] | undefined {
  return job.related_jobs.find((related) => {
    const relatedAction = related.action === "rerun" ? "rerun" : "retry";
    return relatedAction === action && ["inactive", "queued", "running"].includes(related.status);
  });
}

function shortJobId(jobId: string): string {
  return jobId.slice(0, 8);
}

function RetryFailedIcon({ spinning }: { spinning: boolean }): JSX.Element {
  return (
    <span className="relative inline-flex h-4 w-4 items-center justify-center" aria-hidden="true">
      <RotateCcw className={cn("h-4 w-4", spinning && "animate-spin")} />
      <AlertCircle className="absolute -right-1 -top-1 h-2.5 w-2.5 fill-background text-[hsl(var(--warning))]" />
    </span>
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
