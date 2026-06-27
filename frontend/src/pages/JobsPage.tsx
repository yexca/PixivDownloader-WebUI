import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Pause, Play, RefreshCw, XCircle } from "lucide-react";

import {
  bulkCancelJobs,
  cancelJob,
  getJob,
  getJobQueueState,
  listJobs,
  pauseJobQueue,
  resumeJobQueue,
  type Job,
  type JobStatus
} from "@/api/jobs";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { DataState } from "@/components/DataState";
import { JobProgress } from "@/components/JobProgress";
import { JobTable } from "@/components/JobTable";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/Pagination";
import { useToast } from "@/components/ToastProvider";
import { formatDate, isCancellable } from "@/lib/utils";

const statusOptions: Array<{ label: string; value: JobStatus | "" }> = [
  { label: "All statuses", value: "" },
  { label: "Queued", value: "queued" },
  { label: "Running", value: "running" },
  { label: "Completed", value: "completed" },
  { label: "Failed", value: "failed" },
  { label: "Cancelled", value: "cancelled" }
];

export function JobsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const status = (searchParams.get("status") as JobStatus | null) ?? "";
  const page = Math.max(1, Number(searchParams.get("page") || "1"));
  const pageSize = Math.max(1, Number(searchParams.get("pageSize") || "50"));
  const [selectedJobId, setSelectedJobId] = React.useState<string | null>(
    searchParams.get("job")
  );
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(() => new Set());
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const jobs = useQuery({
    queryKey: ["jobs", status || "all", pageSize, page],
    queryFn: () => listJobs({ status, limit: pageSize, offset: (page - 1) * pageSize }),
    refetchInterval: status === "completed" || status === "failed" || status === "cancelled" ? false : 4000
  });
  const queueState = useQuery({
    queryKey: ["job-queue-state"],
    queryFn: getJobQueueState
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
      pushToast({ title: "Cancellation requested", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["job"] });
    },
    onError: (error) => pushToast({ title: "Cancel failed", description: error.message, tone: "error" })
  });
  const bulkCancel = useMutation({
    mutationFn: (jobIds: string[]) => bulkCancelJobs(jobIds),
    onSuccess: (response) => {
      setSelectedIds(new Set());
      pushToast({
        title: "Bulk cancel finished",
        description: `${response.cancelled.length} cancelled, ${response.errors.length} skipped.`,
        tone: response.errors.length ? "warning" : "success"
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
              <Button type="button" variant="outline" onClick={() => resumeQueue.mutate()} disabled={resumeQueue.isPending}>
                <Play className="h-4 w-4" aria-hidden="true" />
                Start Queue
              </Button>
            ) : (
              <Button type="button" variant="outline" onClick={() => pauseQueue.mutate()} disabled={pauseQueue.isPending}>
                <Pause className="h-4 w-4" aria-hidden="true" />
                Stop Queue
              </Button>
            )}
            <Button type="button" variant="outline" asChild>
              <Link to="/jobs/schedules">
                <CalendarClock className="h-4 w-4" aria-hidden="true" />
                Schedules
              </Link>
            </Button>
          </>
        }
      />
      <div className="grid gap-4 p-4 sm:p-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <section className="space-y-3">
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
                      onClick={() => bulkCancel.mutate([...selectedIds])}
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
                    onClick={() => bulkCancel.mutate(queuedJobIds)}
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
                onCancel={(job) => cancelOne.mutate(job)}
                selectedJobId={selectedJobId}
                selectedIds={selectedIds}
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
        <aside className="space-y-3 xl:sticky xl:top-4 xl:max-h-[calc(100vh-2rem)] xl:self-start">
          {selectedJobId && selectedJob.data ? (
            <JobDetailPanel job={selectedJob.data} />
          ) : selectedJob.isLoading ? (
            <DataState title="Loading job detail" variant="loading" />
          ) : selectedJob.isError ? (
            <DataState title="Could not load job" description={selectedJob.error.message} variant="error" />
          ) : (
            <DataState title="Select a job" description="Job events and errors appear here." />
          )}
        </aside>
      </div>
    </>
  );
}

function JobDetailPanel({ job }: { job: Awaited<ReturnType<typeof getJob>> }): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const mutation = useMutation({
    mutationFn: () => cancelJob(job.id),
    onSuccess: () => {
      pushToast({ title: "Cancellation requested", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["job", job.id] });
    },
    onError: (error) => pushToast({ title: "Cancel failed", description: error.message, tone: "error" })
  });

  return (
    <div className="surface flex max-h-[calc(100vh-2rem)] flex-col p-4">
      <div className="shrink-0">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Job Detail</h2>
            <p className="mt-1 break-all text-xs text-muted-foreground">{job.id}</p>
          </div>
          {isCancellable(job.status) ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={mutation.isPending || job.cancel_requested}
              onClick={() => mutation.mutate()}
            >
              <XCircle className="h-4 w-4" aria-hidden="true" />
              Cancel
            </Button>
          ) : null}
        </div>
        <div className="mt-4">
          <JobProgress job={job} />
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

function Detail({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <dt className="text-xs uppercase text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words font-medium">{value}</dd>
    </div>
  );
}
