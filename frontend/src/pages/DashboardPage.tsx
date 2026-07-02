import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, Briefcase, Library, RefreshCw, X, Workflow } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { getDashboardSummary, type DashboardSummary } from "@/api/dashboard";
import { listJobs } from "@/api/jobs";
import { listWorkflowTriggers } from "@/api/workflowTriggers";
import { listWorkflowRuns, type WorkflowRun } from "@/api/workflows";
import { Button } from "@/components/ui/button";
import { DataState } from "@/components/DataState";
import { JobProgress } from "@/components/JobProgress";
import { JobTable } from "@/components/JobTable";
import { PageHeader } from "@/components/PageHeader";
import {
  loadRunJobs,
  RunDetailDialog,
  RunWorkflowCard,
  WorkflowTriggerCard,
  WaitingJobCard,
  WorkflowGroupSection
} from "@/components/workflows/WorkflowRuntimeCards";
import {
  groupRunsByFailureReason,
  latestWorkflowTriggerRun,
  workflowRunGroups,
  workflowTriggerGroups,
  workflowWaitingJobs
} from "@/components/workflows/runtime";
import { useJobStream } from "@/hooks/useJobStream";

export function DashboardPage(): JSX.Element {
  const navigate = useNavigate();
  const [selectedRun, setSelectedRun] = React.useState<WorkflowRun | null>(null);
  const [dismissedRunIds, setDismissedRunIds] = React.useState<Set<string>>(() => new Set());
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
  const triggers = useQuery({
    queryKey: ["workflow-triggers"],
    queryFn: listWorkflowTriggers,
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
  const allTriggers = triggers.data?.items ?? [];
  const runGroups = workflowRunGroups(allRuns);
  const triggerGroups = workflowTriggerGroups(allTriggers);
  const waitingJobs = workflowWaitingJobs(allJobs);
  const visibleFailedRuns = runGroups.failed.filter((run) => !dismissedRunIds.has(run.id));
  const failedRunReasonGroups = groupRunsByFailureReason(visibleFailedRuns);
  const activeJob = allJobs.find((job) => job.status === "running" || job.status === "queued");
  const queueStatus = dashboardQueueStatus(summary.data);
  const stream = useJobStream(activeJob?.id);
  const loading = summary.isLoading || jobs.isLoading || triggers.isLoading || workflowRuns.isLoading;
  const error =
    summary.error?.message ?? jobs.error?.message ?? triggers.error?.message ?? workflowRuns.error?.message;

  function refetchAll() {
    void summary.refetch();
    void jobs.refetch();
    void triggers.refetch();
    void workflowRuns.refetch();
  }

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Workflow runs, trigger health, queue pressure, and library status."
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

        <div className="grid gap-2 md:grid-cols-5">
          <StatusMetric label="Queue" value={queueStatus.label} loading={summary.isLoading} tone={queueStatus.tone} to="/jobs" />
          <StatusMetric label="Active jobs" value={summary.data?.jobs.running ?? 0} loading={summary.isLoading} to="/jobs?status=running" />
          <StatusMetric label="Waiting jobs" value={summary.data?.workflows.waiting_jobs ?? 0} loading={summary.isLoading} to="/jobs" />
          <StatusMetric
            label="Failures"
            value={(summary.data?.library.failed_files ?? 0) + visibleFailedRuns.length}
            loading={loading}
            tone="danger"
            to={visibleFailedRuns.length ? "/runs?filter=failed" : "/library?fileState=failed&sort=failed_desc"}
          />
          <StatusMetric
            label="Updates"
            value={summary.data?.library.artists_with_updates ?? 0}
            loading={summary.isLoading}
            tone="warning"
            to="/library?updateState=available&sort=updated_desc"
          />
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(22rem,0.85fr)] xl:items-start">
          <section className="space-y-4">
            <SectionHeader
              icon={<Workflow className="h-4 w-4" aria-hidden="true" />}
              title="Operations"
              action={<Button asChild size="sm" variant="outline"><Link to="/runs">Open Runs</Link></Button>}
            />
            <div className="surface space-y-4 p-4">
              {loading ? (
                <DataState title="Loading runtime state" variant="loading" />
              ) : activeJob || runGroups.active.length || waitingJobs.length || triggerGroups.active.length ? (
                <>
                  <OperationsGroup
                    title="Active Download"
                    count={activeJob ? 1 : 0}
                    action={<Button asChild size="sm" variant="ghost"><Link to="/jobs?status=running">Open Jobs</Link></Button>}
                  >
                    {activeJob ? <JobProgress job={activeJob} message={stream.lastMessage?.message} /> : null}
                  </OperationsGroup>
                  <OperationsGroup
                    title="Running Runs"
                    count={runGroups.active.length}
                    action={<Button asChild size="sm" variant="ghost"><Link to="/runs?filter=running">Open Runs</Link></Button>}
                  >
                    {runGroups.active.slice(0, 3).map((run) => (
                      <RunWorkflowCard key={run.id} run={run} onInspect={() => setSelectedRun(run)} />
                    ))}
                  </OperationsGroup>
                  <OperationsGroup
                    title="Waiting Queue"
                    count={waitingJobs.length}
                    action={<Button asChild size="sm" variant="ghost"><Link to="/jobs">Open Jobs</Link></Button>}
                  >
                    {waitingJobs.slice(0, 4).map((job) => (
                      <WaitingJobCard key={job.id} job={job} />
                    ))}
                  </OperationsGroup>
                  <OperationsGroup
                    title="Upcoming Schedules"
                    count={triggerGroups.active.length}
                    action={<Button asChild size="sm" variant="ghost"><Link to="/workflows?filter=scheduled">Open Schedules</Link></Button>}
                  >
                    {triggerGroups.active.slice(0, 3).map((task) => (
                      <WorkflowTriggerCard
                        key={task.id}
                        task={task}
                        lastRun={latestWorkflowTriggerRun(task, allRuns)}
                        onRuntimeChanged={refetchAll}
                      />
                    ))}
                  </OperationsGroup>
                </>
              ) : (
                <DataState
                  title="No active work"
                  description="Runs, queued workflow jobs, and live download progress will appear here."
                  actionLabel="Open Workflows"
                  onAction={() => navigate("/workflows")}
                />
              )}
            </div>
          </section>

          <section className="space-y-4">
            <SectionHeader
              icon={<AlertTriangle className="h-4 w-4" aria-hidden="true" />}
              title="Attention"
              action={<Button asChild size="sm" variant="outline"><Link to="/runs">Review</Link></Button>}
            />
            <div className="surface space-y-4 p-4">
              {loading ? (
                <DataState title="Loading attention state" variant="loading" />
              ) : visibleFailedRuns.length || triggerGroups.blocked.length || summaryHasLibraryAttention(summary.data) ? (
                <>
                  {visibleFailedRuns.length ? (
                    <div className="space-y-3">
                      {failedRunReasonGroups.slice(0, 2).map((group) => (
                        <WorkflowGroupSection key={`runs-${group.reason}`} title={`Failed Runs · ${group.reason}`} count={group.items.length}>
                          {group.items.slice(0, 2).map((run) => (
                            <DismissibleRunCard
                              key={run.id}
                              run={run}
                              onInspect={() => setSelectedRun(run)}
                              onDismiss={() => setDismissedRunIds((current) => new Set([...current, run.id]))}
                            />
                          ))}
                        </WorkflowGroupSection>
                      ))}
                    </div>
                  ) : null}
                  {triggerGroups.blocked.length ? (
                    <WorkflowGroupSection title="Blocked Triggers" count={triggerGroups.blocked.length}>
                      {triggerGroups.blocked.slice(0, 2).map((task) => (
                        <WorkflowTriggerCard
                          key={task.id}
                          task={task}
                          lastRun={latestWorkflowTriggerRun(task, allRuns)}
                          onRuntimeChanged={refetchAll}
                        />
                      ))}
                    </WorkflowGroupSection>
                  ) : null}
                  <LibraryAttention
                    failedFiles={summary.data?.library.failed_files ?? 0}
                    artistsWithFailedFiles={summary.data?.library.artists_with_failed_files ?? 0}
                    artistsWithUpdates={summary.data?.library.artists_with_updates ?? 0}
                    unavailableArtists={summary.data?.library.unavailable_artists ?? 0}
                    attentionArtists={summary.data?.library.attention_artists ?? 0}
                  />
                </>
              ) : (
                <DataState title="Nothing needs attention" description="Failures, blocked triggers, and library alerts will appear here." />
              )}
            </div>
          </section>
        </div>

        <section className="space-y-4">
          <SectionHeader
            icon={<Library className="h-4 w-4" aria-hidden="true" />}
            title="Library Snapshot"
            action={<Button asChild size="sm" variant="outline"><Link to="/library">Open Library</Link></Button>}
          />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Artists" value={summary.data?.library.artists ?? 0} loading={summary.isLoading} />
            <Metric label="Artworks" value={summary.data?.library.artworks ?? 0} loading={summary.isLoading} />
            <Metric label="Downloaded files" value={summary.data?.library.downloaded_files ?? 0} loading={summary.isLoading} />
            <Metric label="Pending files" value={summary.data?.library.pending_files ?? 0} loading={summary.isLoading} />
            <Metric label="Artists with updates" value={summary.data?.library.artists_with_updates ?? 0} loading={summary.isLoading} tone="warning" />
            <Metric label="Failed files" value={summary.data?.library.failed_files ?? 0} loading={summary.isLoading} tone="danger" />
            <Metric label="Unavailable artists" value={summary.data?.library.unavailable_artists ?? 0} loading={summary.isLoading} tone="warning" />
            <Metric label="Attention artists" value={summary.data?.library.attention_artists ?? 0} loading={summary.isLoading} tone="warning" />
          </div>
        </section>

        <section>
          <SectionHeader
            icon={<Briefcase className="h-4 w-4" aria-hidden="true" />}
            title="Recent Queue Jobs"
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
            <DataState title="No jobs yet" description="Started workflow jobs will appear here." />
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

function OperationsGroup({
  title,
  count,
  action,
  children
}: {
  title: string;
  count: number;
  action: React.ReactNode;
  children: React.ReactNode;
}): JSX.Element | null {
  if (count === 0) {
    return null;
  }
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">{title}</h3>
          <span className="rounded-md border bg-muted/30 px-2 py-0.5 text-xs font-medium text-muted-foreground">{count}</span>
        </div>
        {action}
      </div>
      <div className="grid gap-3">{children}</div>
    </section>
  );
}

function DismissibleRunCard({
  run,
  onInspect,
  onDismiss
}: {
  run: WorkflowRun;
  onInspect: () => void;
  onDismiss: () => void;
}): JSX.Element {
  return (
    <RunWorkflowCard
      run={run}
      onInspect={onInspect}
      actions={
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="h-7 w-7 text-muted-foreground hover:bg-muted hover:text-foreground"
          title="Hide from dashboard"
          aria-label="Hide from dashboard"
          onClick={onDismiss}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      }
    />
  );
}

function StatusMetric({
  label,
  value,
  loading,
  tone = "default",
  to
}: {
  label: string;
  value: number | string;
  loading: boolean;
  tone?: "default" | "warning" | "danger";
  to: string;
}): JSX.Element {
  const toneClass =
    tone === "danger"
      ? "text-destructive"
      : tone === "warning"
        ? "text-[hsl(var(--warning))]"
        : "text-foreground";
  return (
    <Link
      to={to}
      className="surface flex min-h-20 flex-col justify-between p-3 transition-colors hover:border-primary/50 hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <p className="text-xs font-medium uppercase text-muted-foreground">{label}</p>
      <p className={`text-lg font-semibold ${toneClass}`}>{loading ? "-" : formatMetricValue(value)}</p>
    </Link>
  );
}

function LibraryAttention({
  failedFiles,
  artistsWithFailedFiles,
  artistsWithUpdates,
  unavailableArtists,
  attentionArtists
}: {
  failedFiles: number;
  artistsWithFailedFiles: number;
  artistsWithUpdates: number;
  unavailableArtists: number;
  attentionArtists: number;
}): JSX.Element | null {
  const items = [
    { label: "Failed files", value: failedFiles, tone: "danger" as const },
    { label: "Artists with failed files", value: artistsWithFailedFiles, tone: "danger" as const },
    { label: "Artists with updates", value: artistsWithUpdates, tone: "warning" as const },
    { label: "Unavailable artists", value: unavailableArtists, tone: "warning" as const },
    { label: "Attention artists", value: attentionArtists, tone: "warning" as const }
  ].filter((item) => item.value > 0);
  if (!items.length) {
    return null;
  }
  return (
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
      {items.map((item) => (
        <div key={item.label} className="flex items-center justify-between gap-3 rounded-md border bg-muted/20 px-3 py-2">
          <span className="text-sm text-muted-foreground">{item.label}</span>
          <span className={item.tone === "danger" ? "text-sm font-semibold text-destructive" : "text-sm font-semibold text-[hsl(var(--warning))]"}>
            {item.value.toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  );
}

function summaryHasLibraryAttention(summary: DashboardSummary | undefined): boolean {
  if (!summary) {
    return false;
  }
  return (
    summary.library.failed_files > 0 ||
    summary.library.artists_with_failed_files > 0 ||
    summary.library.artists_with_updates > 0 ||
    summary.library.unavailable_artists > 0 ||
    summary.library.attention_artists > 0
  );
}

function formatMetricValue(value: number | string): string {
  return typeof value === "number" ? value.toLocaleString() : value;
}

function dashboardQueueStatus(summary: DashboardSummary | undefined): {
  label: string;
  tone: "default" | "warning" | "danger";
} {
  if (!summary) {
    return { label: "-", tone: "default" };
  }
  if (summary.queue_paused) {
    return { label: "Paused", tone: "warning" };
  }
  if (summary.jobs.running > 0) {
    return { label: "Active", tone: "default" };
  }
  return { label: "Idle", tone: "default" };
}
