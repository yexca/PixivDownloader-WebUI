import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useSearchParams } from "react-router-dom";
import { RefreshCw, Search } from "lucide-react";

import { listWorkflowDefinitions, listWorkflowRuns, type WorkflowDefinition, type WorkflowRun } from "@/api/workflows";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { WorkflowRunDetail } from "@/components/workflows/WorkflowRunDetail";
import { loadRunJobs } from "@/components/workflows/WorkflowRuntimeCards";
import { cn, formatDate } from "@/lib/utils";
import { sourceLabel, workflowRunTone } from "@/components/workflows/runtime";
import { definitionRunTitle, matchingDefinitionForRun } from "@/components/workflows/definitionMatching";

type RunFilter = "all" | "running" | "completed" | "failed" | "scheduled" | "manual" | "shortcuts" | "system";

const runFilterTabs: Array<{ value: RunFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "scheduled", label: "Scheduled" },
  { value: "manual", label: "Manual" },
  { value: "shortcuts", label: "Shortcuts" },
  { value: "system", label: "System" }
];

const emptyRuns: WorkflowRun[] = [];
const emptyDefinitions: WorkflowDefinition[] = [];
const runsPageStateKey = "pixiv-downloader:runs-page-state";

export function RunsPage(): JSX.Element {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialParamsRef = React.useRef(searchParams.toString() ? searchParams : readPersistedRunsPageState() ?? searchParams);
  const initialParams = initialParamsRef.current;
  const [filter, setFilterState] = React.useState<RunFilter>(runFilterFromParam(initialParams.get("filter")));
  const [search, setSearch] = React.useState(initialParams.get("q") ?? "");
  const [selectedRunId, setSelectedRunId] = React.useState(initialParams.get("run"));
  const defaultRunSyncedRef = React.useRef(Boolean(initialParams.get("run")));

  const runs = useQuery({
    queryKey: ["workflow-runs", 50],
    queryFn: () => listWorkflowRuns(50),
    refetchInterval: 5000
  });
  const definitions = useQuery({
    queryKey: ["workflow-definitions"],
    queryFn: listWorkflowDefinitions,
    refetchInterval: 15000
  });
  const runItems = runs.data?.items ?? emptyRuns;
  const definitionItems = definitions.data?.items ?? emptyDefinitions;
  const filteredRuns = filterRuns(filterRunsByKind(runItems, filter), search);
  const selectedRun = filteredRuns.find((run) => run.id === selectedRunId) ?? filteredRuns[0] ?? null;
  const selectedRunJobs = useQuery({
    queryKey: ["workflow-run-jobs", selectedRun?.id],
    queryFn: () => loadRunJobs(selectedRun),
    enabled: Boolean(selectedRun),
    refetchInterval: selectedRun?.status === "running" ? 4000 : false
  });

  React.useEffect(() => {
    const runId = searchParams.get("run");
    if (runId !== selectedRunId) {
      setSelectedRunId(runId);
      defaultRunSyncedRef.current = Boolean(runId);
    }
  }, [searchParams, selectedRunId]);

  React.useEffect(() => {
    if (location.pathname !== "/runs" || searchParams.toString() || !initialParams.toString()) {
      return;
    }
    setSearchParams(initialParams, { replace: true });
  }, [initialParams, location.pathname, searchParams, setSearchParams]);

  React.useEffect(() => {
    if (location.pathname === "/runs") {
      persistRunsPageState(searchParams);
    }
  }, [location.pathname, searchParams]);

  React.useEffect(() => {
    if (location.pathname !== "/runs" || defaultRunSyncedRef.current || searchParams.get("run") || !selectedRun) {
      return;
    }
    defaultRunSyncedRef.current = true;
    setSelectedRunId(selectedRun.id);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("run", selectedRun.id);
    setSearchParams(nextParams, { replace: true });
  }, [location.pathname, searchParams, selectedRun, setSearchParams]);

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
    defaultRunSyncedRef.current = false;
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
    defaultRunSyncedRef.current = false;
    setSelectedRunId(null);
    setSearchParams(nextParams, { replace: true });
  };
  const selectRun = (run: WorkflowRun) => {
    setSelectedRunId(run.id);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("run", run.id);
    defaultRunSyncedRef.current = true;
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
            <RunList runs={filteredRuns} definitions={definitionItems} selectedRunId={selectedRun?.id ?? null} onSelect={selectRun} />
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
  definitions,
  selectedRunId,
  onSelect
}: {
  runs: WorkflowRun[];
  definitions: WorkflowDefinition[];
  selectedRunId: string | null;
  onSelect: (run: WorkflowRun) => void;
}): JSX.Element {
  if (!runs.length) {
    return <DataState title="No matching runs" description="Try another status or source filter." />;
  }
  return (
    <section className="space-y-2">
      {runs.map((run) => (
        <RunListItem
          key={run.id}
          run={run}
          definition={matchingDefinitionForRun(definitions, run)}
          selected={run.id === selectedRunId}
          onSelect={onSelect}
        />
      ))}
    </section>
  );
}

function RunListItem({
  run,
  definition,
  selected,
  onSelect
}: {
  run: WorkflowRun;
  definition: WorkflowDefinition | null;
  selected: boolean;
  onSelect: (run: WorkflowRun) => void;
}): JSX.Element {
  return (
        <button
          type="button"
          className={cn(
            "w-full rounded-md border bg-card p-3 text-left transition-colors hover:bg-muted/50",
            selected && "border-primary bg-primary/5"
          )}
          onClick={() => onSelect(run)}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold">{definitionRunTitle(definition, run)}</h3>
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
      run.name,
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
  if (filter === "system") {
    return runs.filter((run) => isSystemRun(run));
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

function isSystemRun(run: WorkflowRun): boolean {
  return run.source === "legacy_import" || run.source === "startup_recovery" || run.source.startsWith("system");
}

function runFilterFromParam(value: string | null): RunFilter {
  if (
    value === "running" ||
    value === "completed" ||
    value === "failed" ||
    value === "scheduled" ||
    value === "manual" ||
    value === "shortcuts" ||
    value === "system"
  ) {
    return value;
  }
  return "all";
}

function readPersistedRunsPageState(): URLSearchParams | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const value = window.sessionStorage.getItem(runsPageStateKey);
    return value ? new URLSearchParams(value) : null;
  } catch {
    return null;
  }
}

function persistRunsPageState(params: URLSearchParams): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    if (params.toString()) {
      window.sessionStorage.setItem(runsPageStateKey, params.toString());
    }
  } catch {
    // Storage can be disabled; URL state still keeps the page usable.
  }
}
