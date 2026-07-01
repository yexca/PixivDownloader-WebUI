import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { RefreshCw, Search } from "lucide-react";

import { listWorkflowRuns, type WorkflowRun } from "@/api/workflows";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { WorkflowRunDetail } from "@/components/workflows/WorkflowRunDetail";
import { loadRunJobs } from "@/components/workflows/WorkflowRuntimeCards";
import { cn, formatDate } from "@/lib/utils";
import { runTitle, sourceLabel, workflowRunTone } from "@/components/workflows/runtime";

type RunFilter = "all" | "running" | "completed" | "failed" | "scheduled" | "manual" | "shortcuts";

const runFilterTabs: Array<{ value: RunFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "scheduled", label: "Scheduled" },
  { value: "manual", label: "Manual" },
  { value: "shortcuts", label: "Shortcuts" }
];

const emptyRuns: WorkflowRun[] = [];

export function RunsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filter, setFilterState] = React.useState<RunFilter>(runFilterFromParam(searchParams.get("filter")));
  const [search, setSearch] = React.useState(searchParams.get("q") ?? "");
  const [selectedRunId, setSelectedRunId] = React.useState(searchParams.get("run"));

  const runs = useQuery({
    queryKey: ["workflow-runs", 50],
    queryFn: () => listWorkflowRuns(50),
    refetchInterval: 5000
  });
  const runItems = runs.data?.items ?? emptyRuns;
  const filteredRuns = filterRuns(filterRunsByKind(runItems, filter), search);
  const selectedRun = filteredRuns.find((run) => run.id === selectedRunId) ?? filteredRuns[0] ?? null;
  const selectedRunJobs = useQuery({
    queryKey: ["workflow-run-jobs", selectedRun?.id],
    queryFn: () => loadRunJobs(selectedRun),
    enabled: Boolean(selectedRun),
    refetchInterval: selectedRun?.status === "running" ? 4000 : false
  });

  React.useEffect(() => {
    if (selectedRun && selectedRun.id !== selectedRunId) {
      setSelectedRunId(selectedRun.id);
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set("run", selectedRun.id);
      setSearchParams(nextParams, { replace: true });
    }
  }, [searchParams, selectedRun, selectedRunId, setSearchParams]);

  const refresh = () => {
    void runs.refetch();
    void selectedRunJobs.refetch();
  };
  const setFilter = (nextFilter: RunFilter) => {
    setFilterState(nextFilter);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("filter", nextFilter);
    if (search.trim()) {
      nextParams.set("q", search.trim());
    } else {
      nextParams.delete("q");
    }
    nextParams.delete("run");
    setSelectedRunId(null);
    setSearchParams(nextParams, { replace: true });
  };
  const setSearchQuery = (value: string) => {
    setSearch(value);
    const nextParams = new URLSearchParams(searchParams);
    if (value.trim()) {
      nextParams.set("q", value.trim());
    } else {
      nextParams.delete("q");
    }
    nextParams.delete("run");
    setSelectedRunId(null);
    setSearchParams(nextParams, { replace: true });
  };
  const selectRun = (run: WorkflowRun) => {
    setSelectedRunId(run.id);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("run", run.id);
    setSearchParams(nextParams, { replace: true });
  };

  return (
    <>
      <PageHeader
        title="Run History"
        description="Workflow executions, node progress, embedded jobs, and events."
        actions={
          <Button type="button" variant="outline" onClick={refresh} disabled={runs.isFetching || selectedRunJobs.isFetching}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </Button>
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        <section className="surface p-3">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
            <Tabs value={filter} onValueChange={setFilter} items={runFilterTabs} className="max-w-full flex-wrap" />
            <div className="flex items-center gap-2 text-sm text-muted-foreground xl:ml-auto">
              <Badge tone="muted">{filteredRuns.length}</Badge>
              <span>{runItems.length} recent run(s)</span>
            </div>
            <div className="relative min-w-0 xl:w-80">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={search}
                className="pl-9"
                placeholder="Search runs"
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
          </div>
        </section>

        <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
          <aside className="min-w-0">
          {runs.isLoading ? (
            <DataState title="Loading runs" variant="loading" />
          ) : runs.isError ? (
            <DataState title="Could not load runs" description={runs.error.message} variant="error" />
          ) : (
            <RunList runs={filteredRuns} selectedRunId={selectedRun?.id ?? null} onSelect={selectRun} />
          )}
          </aside>

          <main className="min-w-0">
          {selectedRun ? (
            <WorkflowRunDetail
              run={selectedRun}
              jobs={selectedRunJobs.data ?? []}
              loading={selectedRunJobs.isLoading}
              error={selectedRunJobs.isError ? selectedRunJobs.error.message : undefined}
            />
          ) : (
            <DataState title="No run selected" description="Runs matching the current filter appear in the left list." />
          )}
          </main>
        </div>
      </div>
    </>
  );
}

function RunList({
  runs,
  selectedRunId,
  onSelect
}: {
  runs: WorkflowRun[];
  selectedRunId: string | null;
  onSelect: (run: WorkflowRun) => void;
}): JSX.Element {
  if (!runs.length) {
    return <DataState title="No matching runs" description="Try another status or source filter." />;
  }
  return (
    <section className="space-y-2">
      {runs.map((run) => (
        <button
          key={run.id}
          type="button"
          className={cn(
            "w-full rounded-md border bg-card p-3 text-left transition-colors hover:bg-muted/50",
            run.id === selectedRunId && "border-primary bg-primary/5"
          )}
          onClick={() => onSelect(run)}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold">{runTitle(run)}</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                {sourceLabel(run.source)} · {formatDate(run.created_at)}
              </p>
            </div>
            <Badge tone={workflowRunTone(run.status)}>{run.status}</Badge>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span>{run.completed}/{run.total} nodes</span>
            <span>{run.failed} failed</span>
            <span>{run.node_runs.reduce((total, node) => total + node.job_ids.length, 0)} job(s)</span>
          </div>
        </button>
      ))}
    </section>
  );
}

function filterRuns(runs: WorkflowRun[], search: string): WorkflowRun[] {
  const query = search.trim().toLowerCase();
  if (!query) {
    return runs;
  }
  return runs.filter((run) =>
    [
      run.id,
      run.status,
      run.source,
      sourceLabel(run.source),
      run.node_runs.map((node) => `${node.title} ${node.node_id} ${node.node_type}`).join(" ")
    ]
      .join(" ")
      .toLowerCase()
      .includes(query)
  );
}

function filterRunsByKind(runs: WorkflowRun[], filter: RunFilter): WorkflowRun[] {
  if (filter === "running") {
    return runs.filter((run) => run.status === "running");
  }
  if (filter === "completed") {
    return runs.filter((run) => run.status === "completed" || run.status === "skipped");
  }
  if (filter === "failed") {
    return runs.filter((run) => run.status === "failed" || run.status === "partial");
  }
  if (filter === "scheduled") {
    return runs.filter((run) => isScheduledRun(run));
  }
  if (filter === "manual") {
    return runs.filter((run) => isManualRun(run));
  }
  if (filter === "shortcuts") {
    return runs.filter((run) => isShortcutRun(run));
  }
  return runs;
}

function isScheduledRun(run: WorkflowRun): boolean {
  return run.schedule_id !== null || run.source.includes("schedule") || run.source.includes("trigger");
}

function isManualRun(run: WorkflowRun): boolean {
  return run.source.includes("manual") || run.source === "advanced";
}

function isShortcutRun(run: WorkflowRun): boolean {
  return run.source.includes("shortcut") || run.source.includes("api");
}

function runFilterFromParam(value: string | null): RunFilter {
  if (
    value === "running" ||
    value === "completed" ||
    value === "failed" ||
    value === "scheduled" ||
    value === "manual" ||
    value === "shortcuts"
  ) {
    return value;
  }
  return "all";
}
