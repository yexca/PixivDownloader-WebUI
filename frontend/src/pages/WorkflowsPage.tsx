import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  Activity,
  CheckCircle2,
  Database,
  Eye,
  Filter,
  GitBranch,
  ListChecks,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  UserRoundSearch,
} from "lucide-react";

import {
  listWorkflowDefinitions,
  listWorkflowRuns,
  runWorkflowDefinition,
  type AdvancedWorkflowNode,
  type WorkflowRun,
  type WorkflowDefinition,
  type WorkflowNodeRun
} from "@/api/workflows";
import { listJobs, type Job, type JobDetail } from "@/api/jobs";
import { getSettings, updateSettings } from "@/api/settings";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs } from "@/components/ui/tabs";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { useToast } from "@/components/ToastProvider";
import { AdvancedWorkflowBuilder } from "@/components/workflows/AdvancedWorkflowBuilder";
import { loadRunJobs, RunDetailDialog, WorkflowLimitPanel } from "@/components/workflows/WorkflowRuntimeCards";
import { cn, formatDate, percent } from "@/lib/utils";

type WorkflowView = "definitions" | "runs";
type RunFilter = "all" | "running" | "completed" | "failed" | "scheduled" | "shortcuts";

const viewTabs: Array<{ value: WorkflowView; label: string }> = [
  { value: "definitions", label: "Definitions" },
  { value: "runs", label: "Runs" }
];

const runFilterTabs: Array<{ value: RunFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "scheduled", label: "Scheduled" },
  { value: "shortcuts", label: "Shortcuts" }
];

const emptyDefinitions: WorkflowDefinition[] = [];
const emptyRuns: WorkflowRun[] = [];
const emptyJobs: Job[] = [];

const nodeTypeLabels: Record<string, string> = {
  artist_target: "Target",
  sync_metadata: "Sync",
  collect_artworks: "Collect",
  filter_artworks: "Filter",
  execute_actions: "Action",
  file_output: "Output"
};

const sourceLabels: Record<string, string> = {
  advanced: "one-off",
  advanced_manual: "manual",
  workflow_trigger: "workflow trigger",
  manual_workflow_trigger: "manual workflow trigger",
  manual_schedule: "workflow trigger",
  schedule: "workflow trigger",
  download_api: "download shortcut",
  library_shortcut: "library shortcut",
  artist_api: "library shortcut",
  artwork_file_retry: "file retry",
  import_api: "import"
};

export function WorkflowsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialView = workflowViewFromParam(searchParams.get("view"));
  const [view, setViewState] = React.useState<WorkflowView>(initialView);
  const [runFilter, setRunFilter] = React.useState<RunFilter>(runFilterFromParam(searchParams.get("filter")));
  const [search, setSearch] = React.useState(searchParams.get("q") ?? "");
  const [builderOpen, setBuilderOpen] = React.useState(false);
  const [editingDefinition, setEditingDefinition] = React.useState<WorkflowDefinition | null>(null);
  const [selectedDefinitionId, setSelectedDefinitionId] = React.useState<string | null>(null);
  const [selectedRun, setSelectedRun] = React.useState<WorkflowRun | null>(null);
  const [inspectedRun, setInspectedRun] = React.useState<WorkflowRun | null>(null);

  const definitions = useQuery({
    queryKey: ["workflow-definitions"],
    queryFn: listWorkflowDefinitions,
    refetchInterval: 15000
  });
  const runs = useQuery({
    queryKey: ["workflow-runs", 50],
    queryFn: () => listWorkflowRuns(50),
    refetchInterval: 5000
  });
  const jobs = useQuery({
    queryKey: ["jobs", "workflow-shortcuts", 100],
    queryFn: () => listJobs({ limit: 100 }),
    refetchInterval: 4000
  });
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const selectedRunJobs = useQuery({
    queryKey: ["workflow-run-jobs", selectedRun?.id],
    queryFn: () => loadRunJobs(selectedRun),
    enabled: Boolean(selectedRun),
    refetchInterval: selectedRun?.status === "running" ? 4000 : false
  });
  const inspectedRunJobs = useQuery({
    queryKey: ["workflow-run-jobs", inspectedRun?.id],
    queryFn: () => loadRunJobs(inspectedRun),
    enabled: Boolean(inspectedRun),
    refetchInterval: inspectedRun?.status === "running" ? 4000 : false
  });

  const definitionItems = definitions.data?.items ?? emptyDefinitions;
  const runItems = runs.data?.items ?? emptyRuns;
  const selectedDefinition =
    definitionItems.find((definition) => definition.id === selectedDefinitionId) ?? definitionItems[0] ?? null;
  const filteredDefinitions = filterDefinitions(definitionItems, search);
  const filteredRuns = filterRuns(filterRunsByKind(runItems, runFilter), search);
  const visibleShortcutJobs = filterShortcutJobs(jobs.data?.items ?? emptyJobs, "");

  React.useEffect(() => {
    if (!selectedDefinitionId && definitionItems[0]) {
      setSelectedDefinitionId(definitionItems[0].id);
    }
  }, [definitionItems, selectedDefinitionId]);

  React.useEffect(() => {
    if (view !== "runs") {
      return;
    }
    if (!selectedRun || !filteredRuns.some((run) => run.id === selectedRun.id)) {
      setSelectedRun(filteredRuns[0] ?? null);
    }
  }, [filteredRuns, selectedRun, view]);

  const runDefinition = useMutation({
    mutationFn: runWorkflowDefinition,
    onSuccess: (run) => {
      pushToast({ title: "Workflow started", description: run.id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["workflow-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setInspectedRun(run);
    },
    onError: (error) => pushToast({ title: "Workflow could not start", description: error.message, tone: "error" })
  });
  const limitMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => {
      pushToast({ title: "Run limit synced", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Run limit could not sync", description: error.message, tone: "error" })
  });

  const refresh = () => {
    void definitions.refetch();
    void runs.refetch();
    void jobs.refetch();
  };
  const setView = (nextView: WorkflowView) => {
    setViewState(nextView);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("view", nextView);
    if (search.trim()) {
      nextParams.set("q", search.trim());
    } else {
      nextParams.delete("q");
    }
    setSearchParams(nextParams, { replace: true });
  };
  const setRunFilterParam = (nextFilter: RunFilter) => {
    setRunFilter(nextFilter);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("view", "runs");
    nextParams.set("filter", nextFilter);
    if (search.trim()) {
      nextParams.set("q", search.trim());
    } else {
      nextParams.delete("q");
    }
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
    nextParams.set("view", view);
    setSearchParams(nextParams, { replace: true });
  };
  const openNewBuilder = () => {
    setEditingDefinition(null);
    setBuilderOpen(true);
  };
  const openEditBuilder = (definition: WorkflowDefinition) => {
    setEditingDefinition(definition);
    setBuilderOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Workflows"
        description="Saved workflow definitions, shortcut runs, and node-level execution history."
        actions={
          <>
            <WorkflowLimitPanel
              jobs={jobs.data?.items ?? []}
              settings={settings.data}
              disabled={limitMutation.isPending}
              onSync={(key, value) => limitMutation.mutate({ [key]: value })}
            />
            <Button type="button" variant="outline" onClick={refresh}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Refresh
            </Button>
          </>
        }
      />

      <div className="grid gap-4 p-4 sm:p-6 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
        <aside className="space-y-4">
          <section className="surface p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">Workspace</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {definitionItems.length} definition(s), {runItems.length} recent run(s)
                </p>
              </div>
              <Button type="button" size="sm" onClick={openNewBuilder}>
                <Plus className="h-4 w-4" aria-hidden="true" />
                New
              </Button>
            </div>
            <div className="relative mt-4">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={search}
                className="pl-9"
                placeholder="Search workflows"
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
            <Tabs value={view} onValueChange={setView} items={viewTabs} className="mt-4 max-w-full flex-wrap" />
          </section>

          {view === "definitions" ? (
            <DefinitionList
              definitions={filteredDefinitions}
              selectedDefinitionId={selectedDefinition?.id ?? null}
              loading={definitions.isLoading}
              error={definitions.isError ? definitions.error.message : undefined}
              onSelect={setSelectedDefinitionId}
            />
          ) : (
            <>
              <section className="surface p-3">
                <Tabs value={runFilter} onValueChange={setRunFilterParam} items={runFilterTabs} className="max-w-full flex-wrap" />
              </section>
              <RunList runs={filteredRuns} selectedRunId={selectedRun?.id ?? null} onInspect={setSelectedRun} />
            </>
          )}
        </aside>

        <main className="min-w-0 space-y-4">
          {view === "definitions" ? (
            selectedDefinition ? (
              <DefinitionWorkbench
                definition={selectedDefinition}
                latestRun={latestDefinitionRun(selectedDefinition, runItems)}
                running={runDefinition.isPending}
                onEdit={() => openEditBuilder(selectedDefinition)}
                onRun={() => runDefinition.mutate(selectedDefinition.id)}
                onInspectRun={(run) => setInspectedRun(run)}
              />
            ) : definitions.isLoading ? (
              <DataState title="Loading workflows" variant="loading" />
            ) : (
              <EmptyDefinitionState onCreate={openNewBuilder} />
            )
          ) : selectedRun ? (
            <RunWorkbench
              run={selectedRun}
              jobs={selectedRunJobs.data ?? []}
              loading={selectedRunJobs.isLoading}
              error={selectedRunJobs.isError ? selectedRunJobs.error.message : undefined}
            />
          ) : (
            <DataState title="No run selected" description="Workflow runs matching the current filter appear in the left list." />
          )}
        </main>

        <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          <RuntimeSummary definitions={definitionItems} runs={runItems} jobs={jobs.data?.items ?? []} />
          <ActiveShortcutPanel jobs={visibleShortcutJobs} />
        </aside>
      </div>

      <Dialog
        open={builderOpen}
        title={editingDefinition ? "Edit Workflow" : "Workflow Builder"}
        description={editingDefinition ? editingDefinition.name : "Create a saved definition, a trigger, or a one-off advanced run."}
        className="flex h-[90vh] max-w-6xl flex-col overflow-hidden"
        bodyClassName="min-h-0 flex-1 overflow-hidden"
        onOpenChange={(open) => {
          setBuilderOpen(open);
          if (!open) {
            setEditingDefinition(null);
          }
        }}
      >
        <AdvancedWorkflowBuilder
          definition={editingDefinition}
          onSubmitted={() => {
            setBuilderOpen(false);
            if (editingDefinition) {
              setSelectedDefinitionId(editingDefinition.id);
            }
            setEditingDefinition(null);
            void queryClient.invalidateQueries({ queryKey: ["workflow-definitions"] });
            void queryClient.invalidateQueries({ queryKey: ["workflow-runs"] });
            void queryClient.invalidateQueries({ queryKey: ["jobs"] });
          }}
        />
      </Dialog>

      {view === "definitions" ? (
        <RunDetailDialog
          run={inspectedRun}
          jobs={inspectedRunJobs.data ?? []}
          loading={inspectedRunJobs.isLoading}
          error={inspectedRunJobs.isError ? inspectedRunJobs.error.message : undefined}
          onOpenChange={(open) => {
            if (!open) {
              setInspectedRun(null);
            }
          }}
        />
      ) : null}
    </>
  );
}

function DefinitionList({
  definitions,
  selectedDefinitionId,
  loading,
  error,
  onSelect
}: {
  definitions: WorkflowDefinition[];
  selectedDefinitionId: string | null;
  loading: boolean;
  error?: string;
  onSelect: (definitionId: string) => void;
}): JSX.Element {
  if (loading) {
    return <DataState title="Loading definitions" variant="loading" />;
  }
  if (error) {
    return <DataState title="Could not load definitions" description={error} variant="error" />;
  }
  if (!definitions.length) {
    return <DataState title="No saved workflows" description="Create a definition to reuse or schedule it." />;
  }
  return (
    <section className="space-y-2">
      {definitions.map((definition) => {
        const nodes = workflowNodes(definition);
        const selected = definition.id === selectedDefinitionId;
        return (
          <button
            key={definition.id}
            type="button"
            className={cn(
              "surface w-full p-3 text-left transition-colors hover:bg-muted/50",
              selected && "border-primary bg-primary/5"
            )}
            onClick={() => onSelect(definition.id)}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="truncate text-sm font-semibold">{definition.name}</h3>
                <p className="mt-1 text-xs text-muted-foreground">{nodes.length} node(s)</p>
              </div>
              <Badge tone={definition.triggers.length ? "warning" : "muted"}>
                {definition.triggers.length ? "triggered" : "manual"}
              </Badge>
            </div>
            <div className="mt-3 flex flex-wrap gap-1">
              {nodes.slice(0, 4).map((node) => (
                <Badge key={node.id} tone="muted">
                  {nodeTypeLabel(node.type)}
                </Badge>
              ))}
              {nodes.length > 4 ? <Badge tone="muted">+{nodes.length - 4}</Badge> : null}
            </div>
          </button>
        );
      })}
    </section>
  );
}

function DefinitionWorkbench({
  definition,
  latestRun,
  running,
  onEdit,
  onRun,
  onInspectRun
}: {
  definition: WorkflowDefinition;
  latestRun: WorkflowRun | null;
  running: boolean;
  onEdit: () => void;
  onRun: () => void;
  onInspectRun: (run: WorkflowRun) => void;
}): JSX.Element {
  const nodes = workflowNodes(definition);
  return (
    <>
      <section className="surface p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="break-words text-lg font-semibold">{definition.name}</h2>
              <Badge tone={definition.triggers.length ? "warning" : "muted"}>
                {definition.triggers.length ? `${definition.triggers.length} trigger(s)` : "manual"}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Updated {formatDate(definition.updated_at)} · {definition.id}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={onEdit}>
              <Save className="h-4 w-4" aria-hidden="true" />
              Edit
            </Button>
            <Button type="button" disabled={running} onClick={onRun}>
              <Play className={running ? "h-4 w-4 animate-pulse" : "h-4 w-4"} aria-hidden="true" />
              Run
            </Button>
          </div>
        </div>
      </section>

      <WorkflowGraph nodes={nodes} latestRun={latestRun} />

      {latestRun ? (
        <section className="surface p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-sm font-semibold">Latest Run</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                {runSourceLabel(latestRun)} · {formatDate(latestRun.created_at)}
              </p>
            </div>
            <Button type="button" size="sm" variant="outline" onClick={() => onInspectRun(latestRun)}>
              <Eye className="h-4 w-4" aria-hidden="true" />
              Inspect
            </Button>
          </div>
          <RunNodeTimeline run={latestRun} />
        </section>
      ) : (
        <DataState title="No run yet" description="Run this definition to see node execution here." />
      )}
    </>
  );
}

function WorkflowGraph({ nodes, latestRun }: { nodes: AdvancedWorkflowNode[]; latestRun: WorkflowRun | null }): JSX.Element {
  if (!nodes.length) {
    return <DataState title="Workflow has no nodes" variant="error" />;
  }
  const nodeRuns = latestRun?.node_runs ?? [];
  return (
    <section className="surface overflow-hidden p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Definition Graph</h3>
          <p className="mt-1 text-sm text-muted-foreground">Saved node order and the latest runtime status.</p>
        </div>
        <Badge tone="muted">{nodes.length} nodes</Badge>
      </div>
      <div className="mt-4 overflow-x-auto pb-2">
        <div className="flex min-w-max items-stretch gap-3">
          {nodes.map((node, index) => {
            const run = nodeRuns.find((item) => item.node_id === node.id);
            return (
              <React.Fragment key={node.id}>
                <WorkflowNodeCard node={node} nodeRun={run} />
                {index < nodes.length - 1 ? (
                  <div className="flex w-8 shrink-0 items-center">
                    <div className="h-px flex-1 bg-border" />
                    <GitBranch className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  </div>
                ) : null}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function WorkflowNodeCard({ node, nodeRun }: { node: AdvancedWorkflowNode; nodeRun?: WorkflowNodeRun }): JSX.Element {
  const Icon = nodeIcon(node.type);
  return (
    <article className="w-52 shrink-0 rounded-md border bg-background p-3">
      <div className="flex items-start justify-between gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border bg-muted">
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
        <Badge tone={nodeRun ? workflowStatusTone(nodeRun.status) : "muted"}>
          {nodeRun?.status ?? "ready"}
        </Badge>
      </div>
      <h4 className="mt-3 truncate text-sm font-semibold">{node.title || nodeTypeLabel(node.type)}</h4>
      <p className="mt-1 text-xs text-muted-foreground">{nodeTypeLabel(node.type)} · {node.id}</p>
      <div className="mt-3 space-y-1 text-xs text-muted-foreground">
        <div>{Object.keys(node.config ?? {}).length} config field(s)</div>
        <div>{nodeRun?.job_ids.length ?? 0} linked job(s)</div>
      </div>
    </article>
  );
}

function RunList({
  runs,
  selectedRunId,
  onInspect
}: {
  runs: WorkflowRun[];
  selectedRunId: string | null;
  onInspect: (run: WorkflowRun) => void;
}): JSX.Element {
  if (!runs.length) {
    return <DataState title="No recent runs" description="Workflow executions will appear here." />;
  }
  return (
    <section className="space-y-2">
      {runs.map((run) => (
        <button
          key={run.id}
          type="button"
          className={cn(
            "surface w-full p-3 text-left transition-colors hover:bg-muted/50",
            run.id === selectedRunId && "border-primary bg-primary/5"
          )}
          onClick={() => onInspect(run)}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold">{runTitle(run)}</h3>
              <p className="mt-1 text-xs text-muted-foreground">{runSourceLabel(run)}</p>
            </div>
            <Badge tone={workflowStatusTone(run.status)}>{run.status}</Badge>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            {run.completed}/{run.total} completed · {formatDate(run.created_at)}
          </p>
        </button>
      ))}
    </section>
  );
}

function RunNodeTimeline({ run }: { run: WorkflowRun }): JSX.Element {
  const nodes = run.node_runs;
  if (!nodes.length) {
    return (
      <div className="mt-4 rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">
        No workflow nodes were recorded.
      </div>
    );
  }
  return (
    <div className="mt-4 space-y-2">
      {nodes.map((node) => (
        <div key={node.id ?? node.node_id} className="flex gap-3 rounded-md border bg-muted/20 p-3 text-sm">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border bg-background text-xs font-semibold">
            {node.position + 1}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate font-medium">{node.title}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{node.node_type}</p>
              </div>
              <Badge tone={workflowStatusTone(node.status)}>{node.status}</Badge>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span>{node.job_ids.length} job(s)</span>
              <span>started {formatDate(node.started_at)}</span>
              <span>finished {formatDate(node.finished_at)}</span>
            </div>
            {node.error_message ? <p className="mt-2 text-xs text-destructive">{node.error_message}</p> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

function RuntimeSummary({
  definitions,
  runs,
  jobs
}: {
  definitions: WorkflowDefinition[];
  runs: WorkflowRun[];
  jobs: Job[];
}): JSX.Element {
  const activeRuns = runs.filter((run) => run.status === "running").length;
  const failedRuns = runs.filter((run) => run.status === "failed" || run.status === "partial").length;
  const activeJobs = jobs.filter((job) => job.status === "inactive" || job.status === "queued" || job.status === "running").length;
  return (
    <section className="surface p-4">
      <h2 className="text-sm font-semibold">Runtime</h2>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <SummaryMetric label="Definitions" value={definitions.length} />
        <SummaryMetric label="Active runs" value={activeRuns} tone={activeRuns ? "default" : "normal"} />
        <SummaryMetric label="Active jobs" value={activeJobs} tone={activeJobs ? "default" : "normal"} />
        <SummaryMetric label="Failed runs" value={failedRuns} tone={failedRuns ? "danger" : "normal"} />
      </div>
    </section>
  );
}

function SummaryMetric({
  label,
  value,
  tone = "normal"
}: {
  label: string;
  value: number;
  tone?: "normal" | "default" | "danger";
}): JSX.Element {
  return (
    <div className="rounded-md border bg-muted/25 p-3">
      <p className="text-xs font-medium uppercase text-muted-foreground">{label}</p>
      <p className={cn("mt-2 text-xl font-semibold", tone === "danger" && "text-destructive", tone === "default" && "text-primary")}>
        {value.toLocaleString()}
      </p>
    </div>
  );
}

function ActiveShortcutPanel({ jobs }: { jobs: Job[] }): JSX.Element {
  const activeShortcutJobs = jobs.slice(0, 4);
  return (
    <section className="surface p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Active Shortcuts</h2>
          <p className="mt-1 text-sm text-muted-foreground">Shortcut jobs waiting or running now.</p>
        </div>
        <Badge tone="muted">{jobs.length}</Badge>
      </div>
      <div className="mt-4 space-y-2">
        {activeShortcutJobs.map((job) => (
          <ShortcutJobCard key={job.id} job={job} />
        ))}
        {activeShortcutJobs.length === 0 ? (
          <p className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">No active shortcut jobs.</p>
        ) : null}
      </div>
    </section>
  );
}

function ShortcutJobCard({ job }: { job: Job }): JSX.Element {
  const completed = job.completed_files + job.skipped_files + job.failed_files;
  const progress = percent(completed, job.total_files);
  return (
    <article className="rounded-md border bg-background p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold">{job.type.replaceAll("_", " ")}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{jobTarget(job)}</p>
        </div>
        <Badge tone={jobStatusTone(job.status)}>{job.status}</Badge>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary" style={{ width: `${progress}%` }} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {completed}/{job.total_files || 0} files · {sourceLabel(job.workflow_source ?? "shortcut")}
      </p>
    </article>
  );
}

function EmptyDefinitionState({ onCreate }: { onCreate: () => void }): JSX.Element {
  return (
    <section className="surface p-6 text-center">
      <GitBranch className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
      <h2 className="mt-3 text-base font-semibold">No workflow definition selected</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        Saved definitions are reusable workflows. Shortcut actions from Library still appear as runs.
      </p>
      <Button type="button" className="mt-4" onClick={onCreate}>
        <Plus className="h-4 w-4" aria-hidden="true" />
        New Workflow
      </Button>
    </section>
  );
}

function workflowNodes(definition: WorkflowDefinition): AdvancedWorkflowNode[] {
  const maybeNodes = (definition.definition as { nodes?: unknown }).nodes;
  if (!Array.isArray(maybeNodes)) {
    return [];
  }
  return maybeNodes.filter(isWorkflowNode);
}

function isWorkflowNode(value: unknown): value is AdvancedWorkflowNode {
  if (!value || typeof value !== "object") {
    return false;
  }
  const node = value as Partial<AdvancedWorkflowNode>;
  return typeof node.id === "string" && typeof node.type === "string" && typeof node.config === "object";
}

function filterDefinitions(definitions: WorkflowDefinition[], search: string): WorkflowDefinition[] {
  const query = search.trim().toLowerCase();
  if (!query) {
    return definitions;
  }
  return definitions.filter((definition) =>
    [definition.name, definition.id, workflowNodes(definition).map((node) => `${node.type} ${node.title ?? ""}`).join(" ")]
      .join(" ")
      .toLowerCase()
      .includes(query)
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
      runSourceLabel(run),
      run.node_runs.map((node) => `${node.title} ${node.node_id} ${node.node_type}`).join(" ")
    ]
      .join(" ")
      .toLowerCase()
      .includes(query)
  );
}

function filterShortcutJobs(jobs: Job[], search: string): Job[] {
  const query = search.trim().toLowerCase();
  return jobs
    .filter((job) => isShortcutJob(job) && isActiveJob(job))
    .filter((job) =>
      query
        ? [job.id, job.type, job.workflow_source, job.input_user_id, job.input_artwork_id, job.status].join(" ").toLowerCase().includes(query)
        : true
    );
}

function latestDefinitionRun(definition: WorkflowDefinition, runs: WorkflowRun[]): WorkflowRun | null {
  const triggerIds = new Set(definition.triggers.map((trigger) => trigger.id));
  const matches = runs.filter((run) => run.schedule_id !== null && triggerIds.has(run.schedule_id));
  return matches[0] ?? null;
}

function RunWorkbench({
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
            <Badge tone={workflowStatusTone(run.status)}>{run.status}</Badge>
            <Badge tone="muted">{runSourceLabel(run)}</Badge>
          </div>
          <p className="mt-1 break-all text-sm text-muted-foreground">{run.id}</p>
        </div>
        <dl className="grid gap-3 text-sm sm:grid-cols-4 lg:min-w-[520px]">
          <RunMetric label="Completed" value={`${run.completed}/${run.total}`} />
          <RunMetric label="Failed" value={String(run.failed)} />
          <RunMetric label="Created" value={formatDate(run.created_at)} />
          <RunMetric label="Finished" value={formatDate(run.finished_at)} />
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
                    <Badge tone={workflowStatusTone(node.status)}>{node.status}</Badge>
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
            <NodeWorkbench node={selectedNode} jobs={selectedNodeJobs} loading={loading} error={error} />
          ) : (
            <DataState title="No node selected" description="Select a workflow node to inspect its runtime data." />
          )}
        </div>
      </div>
    </section>
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
  if (filter === "shortcuts") {
    return runs.filter((run) => isShortcutRun(run));
  }
  return runs;
}

function NodeWorkbench({
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
              <Badge tone={workflowStatusTone(node.status)}>{node.status}</Badge>
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
          <RunMetric label="Started" value={formatDate(node.started_at)} />
          <RunMetric label="Finished" value={formatDate(node.finished_at)} />
          <RunMetric label="Jobs" value={String(node.job_ids.length)} />
          <RunMetric label="Files" value={loading ? "Loading" : error ? "-" : `${completedFiles} ok / ${failedFiles} failed`} />
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

function RunMetric({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <dt className="text-xs uppercase text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words font-medium">{value}</dd>
    </div>
  );
}

function isShortcutRun(run: WorkflowRun): boolean {
  return run.source.includes("shortcut") || run.source.includes("api");
}

function isScheduledRun(run: WorkflowRun): boolean {
  return run.schedule_id !== null || run.source.includes("schedule") || run.source.includes("trigger");
}

function isShortcutJob(job: Job): boolean {
  const source = job.workflow_source ?? "";
  return source.includes("shortcut") || source.includes("api") || source === "download_api";
}

function isActiveJob(job: Job): boolean {
  return job.status === "inactive" || job.status === "queued" || job.status === "running";
}

function nodeTypeLabel(type: string): string {
  return nodeTypeLabels[type] ?? type.replaceAll("_", " ");
}

function sourceLabel(source: string): string {
  return sourceLabels[source] ?? source.replaceAll("_", " ");
}

function runSourceLabel(run: WorkflowRun): string {
  return sourceLabel(run.source);
}

function runTitle(run: WorkflowRun): string {
  if (run.node_runs.length) {
    return run.node_runs[0]?.title || `${run.node_runs.length} node workflow`;
  }
  return "Workflow run";
}

function jobTarget(job: Job): string {
  if (job.input_user_id) {
    return `Artist ${job.input_user_id}`;
  }
  if (job.input_artwork_id) {
    return `Artwork ${job.input_artwork_id}`;
  }
  return "No target";
}

function nodeIcon(type: string): React.ComponentType<{ className?: string; "aria-hidden"?: boolean }> {
  if (type === "artist_target") {
    return UserRoundSearch;
  }
  if (type === "sync_metadata") {
    return Database;
  }
  if (type === "collect_artworks") {
    return ListChecks;
  }
  if (type === "filter_artworks") {
    return Filter;
  }
  if (type === "execute_actions") {
    return Play;
  }
  if (type === "file_output") {
    return CheckCircle2;
  }
  return Activity;
}

function workflowStatusTone(status: string): "default" | "success" | "danger" | "warning" | "muted" {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed" || status === "partial" || status === "cancelled") {
    return "danger";
  }
  if (status === "running" || status === "queued") {
    return "default";
  }
  if (status === "pending" || status === "skipped") {
    return "warning";
  }
  return "muted";
}

function jobStatusTone(status: Job["status"]): "default" | "success" | "danger" | "warning" | "muted" {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed" || status === "cancelled") {
    return "danger";
  }
  if (status === "running" || status === "queued") {
    return "default";
  }
  return "warning";
}

function workflowViewFromParam(value: string | null): WorkflowView {
  if (value === "runs" || value === "shortcuts") {
    return "runs";
  }
  return "definitions";
}

function runFilterFromParam(value: string | null): RunFilter {
  if (value === "running" || value === "completed" || value === "failed" || value === "scheduled" || value === "shortcuts") {
    return value;
  }
  return "all";
}

function timeValue(value: string | null): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
