import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, XCircle } from "lucide-react";

import { cancelJob, getJob, listJobs, type Job, type JobStatus } from "@/api/jobs";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { DataState } from "@/components/DataState";
import { JobProgress } from "@/components/JobProgress";
import { JobTable } from "@/components/JobTable";
import { PageHeader } from "@/components/PageHeader";
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
  const [status, setStatus] = React.useState<JobStatus | "">("");
  const [selectedJobId, setSelectedJobId] = React.useState<string | null>(
    searchParams.get("job")
  );
  const jobs = useQuery({
    queryKey: ["jobs", status || "all", 50],
    queryFn: () => listJobs({ status, limit: 50 }),
    refetchInterval: status === "completed" || status === "failed" || status === "cancelled" ? false : 4000
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

  React.useEffect(() => {
    if (!selectedJobId || !jobs.isSuccess) {
      return;
    }
    const row = document.getElementById(`job-${selectedJobId}`);
    row?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [jobs.isSuccess, selectedJobId]);

  const selectJob = (job: Job) => {
    setSelectedJobId(job.id);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("job", job.id);
    setSearchParams(nextParams, { replace: true });
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
                setStatus(event.target.value as JobStatus | "");
                setSelectedJobId(null);
                setSearchParams({}, { replace: true });
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
          </>
        }
      />
      <div className="grid gap-4 p-4 sm:p-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <section>
          {jobs.isLoading ? (
            <DataState title="Loading jobs" variant="loading" />
          ) : jobs.isError ? (
            <DataState title="Could not load jobs" description={jobs.error.message} variant="error" />
          ) : jobs.data.items.length === 0 ? (
            <DataState title="No jobs found" description="Try another status filter or start a download." />
          ) : (
            <JobTable
              jobs={jobs.data.items}
              onSelect={selectJob}
              selectedJobId={selectedJobId}
            />
          )}
        </section>
        <aside className="space-y-3">
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
    <div className="surface p-4">
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
      {job.events.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">No events recorded.</p>
      ) : (
        <div className="mt-3 max-h-80 space-y-2 overflow-auto">
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
