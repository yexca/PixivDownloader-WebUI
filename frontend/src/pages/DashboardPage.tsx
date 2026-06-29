import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, Briefcase, CalendarClock, Library, RefreshCw, Workflow } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { getDashboardSummary } from "@/api/dashboard";
import { listJobs } from "@/api/jobs";
import { listScheduledTasks } from "@/api/scheduledTasks";
import { listWorkflowRuns, type WorkflowBatchRun } from "@/api/workflows";
import { Button } from "@/components/ui/button";
import { DataState } from "@/components/DataState";
import { JobProgress } from "@/components/JobProgress";
import { JobTable } from "@/components/JobTable";
import { PageHeader } from "@/components/PageHeader";
import {
  loadRunJobs,
  RunDetailDialog,
  RunWorkflowCard,
  ScheduleWorkflowCard,
  WaitingJobCard,
  WorkflowGroupSection
} from "@/components/workflows/WorkflowRuntimeCards";
import {
  groupRunsByFailureReason,
  groupSchedulesByFailureReason,
  latestScheduleRun,
  workflowRunGroups,
  workflowScheduleGroups,
  workflowWaitingJobs
} from "@/components/workflows/runtime";
import { useJobStream } from "@/hooks/useJobStream";

export function DashboardPage(): JSX.Element {
  const navigate = useNavigate();
  const [selectedRun, setSelectedRun] = React.useState<WorkflowBatchRun | null>(null);
  const summary = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboardSummary,
    refetchInterval: 5000
  });
  const jobs = useQuery({
    queryKey: ["jobs", "dashboard", 100],
    queryFn: () => listJobs({ limit: 100 }),
    refetchInterval: 4000
  });
  const schedules = useQuery({
    queryKey: ["scheduled-tasks"],
    queryFn: listScheduledTasks,
    refetchInterval: 15000
  });
  const workflowRuns = useQuery({
    queryKey: ["workflow-runs", 50],
    queryFn: () => listWorkflowRuns(50),
    refetchInterval: 10000
  });
  const selectedRunJobs = useQuery({
    queryKey: ["workflow-run-jobs", selectedRun?.id],
    queryFn: () => loadRunJobs(selectedRun),
    enabled: Boolean(selectedRun),
    refetchInterval: selectedRun?.status === "running" ? 4000 : false
  });

  const allJobs = jobs.data?.items ?? [];
  const allRuns = workflowRuns.data?.items ?? [];
  const allSchedules = schedules.data?.items ?? [];
  const runGroups = workflowRunGroups(allRuns);
  const scheduleGroups = workflowScheduleGroups(allSchedules);
  const waitingJobs = workflowWaitingJobs(allJobs);
  const failedRunReasonGroups = groupRunsByFailureReason(runGroups.failed);
  const blockedScheduleReasonGroups = groupSchedulesByFailureReason(scheduleGroups.blocked);
  const activeJob = allJobs.find((job) => job.status === "running" || job.status === "queued");
  const stream = useJobStream(activeJob?.id);
  const loading = summary.isLoading || jobs.isLoading || schedules.isLoading || workflowRuns.isLoading;
  const error =
    summary.error?.message ?? jobs.error?.message ?? schedules.error?.message ?? workflowRuns.error?.message;

  function refetchAll() {
    void summary.refetch();
    void jobs.refetch();
    void schedules.refetch();
    void workflowRuns.refetch();
  }

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Workflow runs, schedule health, queue pressure, and library status."
        actions={
          <>
            <Button type="button" variant="outline" onClick={refetchAll} disabled={summary.isFetching || jobs.isFetching}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Refresh
            </Button>
            <Button asChild>
              <Link to="/workflows">
                <Workflow className="h-4 w-4" aria-hidden="true" />
                New Workflow
              </Link>
            </Button>
          </>
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        {error ? <DataState title="Could not load dashboard" description={error} variant="error" /> : null}

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Metric label="Running runs" value={summary.data?.workflows.running_runs ?? 0} loading={summary.isLoading} />
          <Metric label="Waiting queue" value={summary.data?.workflows.waiting_jobs ?? 0} loading={summary.isLoading} />
          <Metric label="Blocked schedules" value={summary.data?.workflows.blocked_schedules ?? 0} loading={summary.isLoading} tone="warning" />
          <Metric label="Failed files" value={summary.data?.library.failed_files ?? 0} loading={summary.isLoading} tone="danger" />
          <Metric label="Artist updates" value={summary.data?.library.artists_with_updates ?? 0} loading={summary.isLoading} tone="warning" />
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(340px,0.8fr)]">
          <section className="space-y-4">
            <SectionHeader
              icon={<Workflow className="h-4 w-4" aria-hidden="true" />}
              title="Active Work"
              action={<Button asChild size="sm" variant="outline"><Link to="/workflows">Open Workflows</Link></Button>}
            />
            {loading ? (
              <DataState title="Loading workflow state" variant="loading" />
            ) : runGroups.active.length || waitingJobs.length ? (
              <div className="space-y-4">
                <WorkflowGroupSection title="Running Runs" count={runGroups.active.length}>
                  {runGroups.active.slice(0, 3).map((run) => (
                    <RunWorkflowCard key={run.id} run={run} onInspect={() => setSelectedRun(run)} />
                  ))}
                </WorkflowGroupSection>
                <WorkflowGroupSection title="Waiting Queue" count={waitingJobs.length}>
                  {waitingJobs.slice(0, 3).map((job) => (
                    <WaitingJobCard key={job.id} job={job} />
                  ))}
                </WorkflowGroupSection>
              </div>
            ) : activeJob ? (
              <JobProgress job={activeJob} message={stream.lastMessage?.message} />
            ) : (
              <DataState
                title="No active workflow"
                description="Stage a workflow when you are ready."
                actionLabel="Open Workflows"
                onAction={() => navigate("/workflows")}
              />
            )}
          </section>

          <section className="space-y-4">
            <SectionHeader
              icon={<CalendarClock className="h-4 w-4" aria-hidden="true" />}
              title="Schedules"
              action={<Button asChild size="sm" variant="outline"><Link to="/workflows">Manage</Link></Button>}
            />
            {loading ? (
              <DataState title="Loading schedules" variant="loading" />
            ) : scheduleGroups.blocked.length ? (
              <WorkflowGroupSection title="Blocked Schedules" count={scheduleGroups.blocked.length}>
                {scheduleGroups.blocked.slice(0, 3).map((task) => (
                  <ScheduleWorkflowCard
                    key={task.id}
                    task={task}
                    lastRun={latestScheduleRun(task, allRuns)}
                    onRuntimeChanged={refetchAll}
                  />
                ))}
              </WorkflowGroupSection>
            ) : scheduleGroups.active.length ? (
              <WorkflowGroupSection title="Active Schedules" count={scheduleGroups.active.length}>
                {scheduleGroups.active.slice(0, 3).map((task) => (
                  <ScheduleWorkflowCard
                    key={task.id}
                    task={task}
                    lastRun={latestScheduleRun(task, allRuns)}
                    onRuntimeChanged={refetchAll}
                  />
                ))}
              </WorkflowGroupSection>
            ) : (
              <DataState title="No active schedules" description="Scheduled workflows will appear here." />
            )}
          </section>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <section className="space-y-4">
            <SectionHeader
              icon={<AlertTriangle className="h-4 w-4" aria-hidden="true" />}
              title="Failures"
              action={<Button asChild size="sm" variant="outline"><Link to="/jobs">Open Jobs</Link></Button>}
            />
            {loading ? (
              <DataState title="Loading failures" variant="loading" />
            ) : runGroups.failed.length || scheduleGroups.blocked.length ? (
              <div className="space-y-4">
                {failedRunReasonGroups.slice(0, 2).map((group) => (
                  <WorkflowGroupSection key={`runs-${group.reason}`} title={`Failed Runs · ${group.reason}`} count={group.items.length}>
                    {group.items.slice(0, 2).map((run) => (
                      <RunWorkflowCard key={run.id} run={run} onInspect={() => setSelectedRun(run)} />
                    ))}
                  </WorkflowGroupSection>
                ))}
                {blockedScheduleReasonGroups.slice(0, 2).map((group) => (
                  <WorkflowGroupSection key={`schedules-${group.reason}`} title={`Blocked Schedules · ${group.reason}`} count={group.items.length}>
                    {group.items.slice(0, 2).map((task) => (
                      <ScheduleWorkflowCard
                        key={task.id}
                        task={task}
                        lastRun={latestScheduleRun(task, allRuns)}
                        onRuntimeChanged={refetchAll}
                      />
                    ))}
                  </WorkflowGroupSection>
                ))}
              </div>
            ) : (
              <DataState title="No workflow failures" description="Failed runs and blocked schedules will appear here." />
            )}
          </section>

          <section className="space-y-4">
            <SectionHeader
              icon={<Library className="h-4 w-4" aria-hidden="true" />}
              title="Library Health"
              action={<Button asChild size="sm" variant="outline"><Link to="/library">Open Library</Link></Button>}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Metric label="Artists" value={summary.data?.library.artists ?? 0} loading={summary.isLoading} />
              <Metric label="Artworks" value={summary.data?.library.artworks ?? 0} loading={summary.isLoading} />
              <Metric label="Downloaded files" value={summary.data?.library.downloaded_files ?? 0} loading={summary.isLoading} />
              <Metric label="Pending files" value={summary.data?.library.pending_files ?? 0} loading={summary.isLoading} />
              <Metric label="Artists with updates" value={summary.data?.library.artists_with_updates ?? 0} loading={summary.isLoading} tone="warning" />
              <Metric label="Artists with failed files" value={summary.data?.library.artists_with_failed_files ?? 0} loading={summary.isLoading} tone="danger" />
              <Metric label="Unavailable artists" value={summary.data?.library.unavailable_artists ?? 0} loading={summary.isLoading} tone="warning" />
              <Metric label="Attention artists" value={summary.data?.library.attention_artists ?? 0} loading={summary.isLoading} tone="warning" />
            </div>
            <div className="surface p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold">Queue</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {summary.data?.queue_paused ? "Paused" : "Running"} · {summary.data?.jobs.running ?? 0} running, {summary.data?.jobs.queued ?? 0} queued
                  </p>
                </div>
                <Button asChild size="sm" variant="outline">
                  <Link to="/jobs">
                    <Briefcase className="h-4 w-4" aria-hidden="true" />
                    Inspect
                  </Link>
                </Button>
              </div>
            </div>
          </section>
        </div>

        <section>
          <SectionHeader
            icon={<Briefcase className="h-4 w-4" aria-hidden="true" />}
            title="Recent Jobs"
            action={<Button type="button" variant="ghost" size="sm" onClick={() => void jobs.refetch()} disabled={jobs.isFetching}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Refresh
            </Button>}
          />
          {jobs.isLoading ? (
            <DataState title="Loading jobs" variant="loading" />
          ) : jobs.isError ? (
            <DataState title="Could not load jobs" description={jobs.error.message} variant="error" />
          ) : allJobs.length === 0 ? (
            <DataState title="No jobs yet" description="Started workflows will appear here." />
          ) : (
            <JobTable jobs={allJobs.slice(0, 10)} onSelect={(job) => navigate(`/jobs?job=${encodeURIComponent(job.id)}`)} />
          )}
        </section>
      </div>

      <RunDetailDialog
        run={selectedRun}
        jobs={selectedRunJobs.data ?? []}
        loading={selectedRunJobs.isLoading}
        error={selectedRunJobs.error?.message}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedRun(null);
          }
        }}
      />
    </>
  );
}

function SectionHeader({
  icon,
  title,
  action
}: {
  icon: React.ReactNode;
  title: string;
  action?: React.ReactNode;
}): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        {icon}
        <h2 className="text-sm font-semibold">{title}</h2>
      </div>
      {action}
    </div>
  );
}

function Metric({
  label,
  value,
  loading,
  tone = "default"
}: {
  label: string;
  value: number;
  loading: boolean;
  tone?: "default" | "warning" | "danger";
}): JSX.Element {
  const toneClass =
    tone === "danger"
      ? "text-destructive"
      : tone === "warning"
        ? "text-[hsl(var(--warning))]"
        : "text-foreground";
  return (
    <div className="surface p-4">
      <p className="text-xs font-medium uppercase text-muted-foreground">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${toneClass}`}>{loading ? "-" : value.toLocaleString()}</p>
    </div>
  );
}
