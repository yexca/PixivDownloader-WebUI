import * as React from "react";

import type { JobDetail } from "@/api/jobs";
import type { WorkflowNodeRun, WorkflowRun } from "@/api/workflows";
import { Badge } from "@/components/ui/badge";
import { DataState } from "@/components/DataState";
import { cn, formatDate } from "@/lib/utils";
import { jobStatusTone, jobTarget, runTitle, sourceLabel, workflowRunTone } from "./runtime";

export function WorkflowRunDetail({
  run,
  jobs,
  loading,
  error
}: {
  run: WorkflowRun;
  jobs: JobDetail[];
  loading: boolean;
  error?: string;
}): JSX.Element {
  const [selectedNodeId, setSelectedNodeId] = React.useState(run.node_runs[0]?.node_id ?? null);
  const selectedNode = run.node_runs.find((node) => node.node_id === selectedNodeId) ?? run.node_runs[0] ?? null;
  const selectedNodeJobs = selectedNode ? jobs.filter((job) => selectedNode.job_ids.includes(job.id)) : [];

  React.useEffect(() => {
    setSelectedNodeId(run.node_runs[0]?.node_id ?? null);
  }, [run.id, run.node_runs]);

  return (
    <section className="surface min-w-0 p-4">
      <div className="flex flex-col gap-3 border-b pb-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-lg font-semibold">{runTitle(run)}</h2>
            <Badge tone={workflowRunTone(run.status)}>{run.status}</Badge>
            <Badge tone="muted">{sourceLabel(run.source)}</Badge>
          </div>
          <p className="mt-1 break-all text-sm text-muted-foreground">{run.id}</p>
        </div>
        <dl className="grid gap-3 text-sm sm:grid-cols-4 lg:min-w-[520px]">
          <Detail label="Completed" value={`${run.completed}/${run.total}`} />
          <Detail label="Failed" value={String(run.failed)} />
          <Detail label="Created" value={formatDate(run.created_at)} />
          <Detail label="Finished" value={formatDate(run.finished_at)} />
        </dl>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="min-w-0 space-y-2">
          <h3 className="px-1 text-sm font-semibold">Node Timeline</h3>
          {run.node_runs.length ? (
            run.node_runs.map((node) => {
              const selected = selectedNode?.node_id === node.node_id;
              return (
                <button
                  key={node.id ?? node.node_id}
                  type="button"
                  className={cn(
                    "w-full rounded-md border bg-background p-3 text-left text-sm transition-colors hover:bg-muted/50",
                    selected && "border-primary bg-primary/5"
                  )}
                  onClick={() => setSelectedNodeId(node.node_id)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{node.title}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {node.position + 1}. {node.node_type}
                      </p>
                    </div>
                    <Badge tone={workflowRunTone(node.status)}>{node.status}</Badge>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{node.job_ids.length} job(s)</p>
                </button>
              );
            })
          ) : (
            <p className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">No workflow nodes were recorded.</p>
          )}
        </aside>

        <div className="min-w-0">
          {selectedNode ? (
            <NodeDetail node={selectedNode} jobs={selectedNodeJobs} loading={loading} error={error} />
          ) : (
            <DataState title="No node selected" description="Select a workflow node to inspect its runtime data." />
          )}
        </div>
      </div>
    </section>
  );
}

function NodeDetail({
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
    <div className="space-y-4">
      <section className="rounded-md border bg-card p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="break-words text-base font-semibold">{node.title}</h3>
              <Badge tone={workflowRunTone(node.status)}>{node.status}</Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {node.position + 1}. {node.node_type} · {node.node_id}
            </p>
          </div>
        </div>
        {node.error_message ? (
          <p className="mt-4 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
            {node.error_message}
          </p>
        ) : null}
      </section>

      <section className="rounded-md border bg-card p-4">
        <dl className="grid gap-3 text-sm sm:grid-cols-4">
          <Detail label="Started" value={formatDate(node.started_at)} />
          <Detail label="Finished" value={formatDate(node.finished_at)} />
          <Detail label="Jobs" value={String(node.job_ids.length)} />
          <Detail label="Files" value={loading ? "Loading" : error ? "-" : `${completedFiles} ok / ${failedFiles} failed`} />
        </dl>
      </section>

      {error ? <DataState title="Could not load jobs" description={error} variant="error" /> : null}
      {!error && jobs.length ? (
        <section className="space-y-3">
          {jobs.map((job) => (
            <RunJobSummary key={job.id} job={job} />
          ))}
        </section>
      ) : null}
      {!loading && !error && !jobs.length ? (
        <p className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">No jobs were linked to this node.</p>
      ) : null}
    </div>
  );
}

function RunJobSummary({ job }: { job: JobDetail }): JSX.Element {
  const latestEvent = [...job.events].sort((left, right) => timeValue(right.created_at) - timeValue(left.created_at))[0];
  return (
    <article className="rounded-md border bg-card p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="break-words text-sm font-semibold">{job.type.replaceAll("_", " ")}</h4>
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
      ) : latestEvent ? (
        <p className="mt-3 rounded-md border bg-muted/20 p-2 text-xs">{latestEvent.message}</p>
      ) : null}
    </article>
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

function timeValue(value: string | null): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
