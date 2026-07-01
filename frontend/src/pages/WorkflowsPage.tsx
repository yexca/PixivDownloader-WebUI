import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  Activity,
  CheckCircle2,
  Database,
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
import { listJobs, type Job } from "@/api/jobs";
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
import { WorkflowLimitPanel } from "@/components/workflows/WorkflowRuntimeCards";
import { cn, formatDate, percent } from "@/lib/utils";

type DefinitionFilter = "manual" | "scheduled";

const definitionFilterTabs: Array<{ value: DefinitionFilter; label: string }> = [
  { value: "manual", label: "Manual" },
  { value: "scheduled", label: "Scheduled" }
];

const emptyDefinitions: WorkflowDefinition[] = [];
const emptyRuns: WorkflowRun[] = [];

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
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [definitionFilter, setDefinitionFilter] = React.useState<DefinitionFilter>(
    definitionFilterFromParam(searchParams.get("filter"))
  );
  const [search, setSearch] = React.useState(searchParams.get("q") ?? "");
  const [builderOpen, setBuilderOpen] = React.useState(false);
  const [editingDefinition, setEditingDefinition] = React.useState<WorkflowDefinition | null>(null);
  const [selectedDefinitionId, setSelectedDefinitionId] = React.useState<string | null>(null);

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

  const definitionItems = definitions.data?.items ?? emptyDefinitions;
  const runItems = runs.data?.items ?? emptyRuns;
  const filteredDefinitions = React.useMemo(
    () => filterDefinitions(filterDefinitionsByKind(definitionItems, definitionFilter), search),
    [definitionFilter, definitionItems, search]
  );
  const selectedDefinition =
    filteredDefinitions.find((definition) => definition.id === selectedDefinitionId) ?? filteredDefinitions[0] ?? null;
  const visibleShortcutJobs = filterShortcutJobs(jobs.data?.items ?? [], "");

  React.useEffect(() => {
    if (!selectedDefinitionId && definitionItems[0]) {
      setSelectedDefinitionId(definitionItems[0].id);
    }
  }, [definitionItems, selectedDefinitionId]);

  React.useEffect(() => {
    if (!filteredDefinitions.length) {
      setSelectedDefinitionId(null);
      return;
    }
    if (!selectedDefinitionId || !filteredDefinitions.some((definition) => definition.id === selectedDefinitionId)) {
      setSelectedDefinitionId(filteredDefinitions[0].id);
    }
  }, [filteredDefinitions, selectedDefinitionId]);

  const runDefinition = useMutation({
    mutationFn: runWorkflowDefinition,
    onSuccess: (run) => {
      pushToast({ title: "Workflow started", description: run.id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["workflow-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      navigate(`/runs?run=${encodeURIComponent(run.id)}`);
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
  const setDefinitionFilterParam = (nextFilter: DefinitionFilter) => {
    setDefinitionFilter(nextFilter);
    const nextParams = new URLSearchParams(searchParams);
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
        description="Create, run, and schedule reusable workflow definitions."
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
            <Tabs
              value={definitionFilter}
              onValueChange={setDefinitionFilterParam}
              items={definitionFilterTabs}
              className="mt-4 max-w-full flex-wrap"
            />
          </section>

          <DefinitionList
            definitions={filteredDefinitions}
            selectedDefinitionId={selectedDefinition?.id ?? null}
            loading={definitions.isLoading}
            error={definitions.isError ? definitions.error.message : undefined}
            onSelect={setSelectedDefinitionId}
          />
        </aside>

        <main className="min-w-0 space-y-4">
          {selectedDefinition ? (
            <DefinitionWorkbench
              definition={selectedDefinition}
              latestRun={latestDefinitionRun(selectedDefinition, runItems)}
              running={runDefinition.isPending}
              onEdit={() => openEditBuilder(selectedDefinition)}
              onRun={() => runDefinition.mutate(selectedDefinition.id)}
            />
          ) : definitions.isLoading ? (
            <DataState title="Loading workflows" variant="loading" />
          ) : (
            <EmptyDefinitionState onCreate={openNewBuilder} />
          )}
        </main>

        <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          <RuntimeSummary definitions={definitionItems} runs={runItems} jobs={jobs.data?.items ?? []} />
          <RecentRunsPanel runs={runItems} />
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
  onRun
}: {
  definition: WorkflowDefinition;
  latestRun: WorkflowRun | null;
  running: boolean;
  onEdit: () => void;
  onRun: () => void;
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
            <Button type="button" size="sm" variant="outline" asChild>
              <Link to={`/runs?run=${encodeURIComponent(latestRun.id)}`}>Open Run</Link>
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

function RecentRunsPanel({ runs }: { runs: WorkflowRun[] }): JSX.Element {
  const recentRuns = runs.slice(0, 4);
  return (
    <section className="surface p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Recent Runs</h2>
          <p className="mt-1 text-sm text-muted-foreground">Open execution details in Runs.</p>
        </div>
        <Button type="button" size="sm" variant="outline" asChild>
          <Link to="/runs">All</Link>
        </Button>
      </div>
      <div className="mt-4 space-y-2">
        {recentRuns.map((run) => (
          <Link
            key={run.id}
            to={`/runs?run=${encodeURIComponent(run.id)}`}
            className="block rounded-md border bg-background p-3 text-sm transition-colors hover:bg-muted/50"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{runTitle(run)}</span>
              <Badge tone={workflowStatusTone(run.status)}>{run.status}</Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {runSourceLabel(run)} · {formatDate(run.created_at)}
            </p>
          </Link>
        ))}
        {recentRuns.length === 0 ? (
          <p className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">No workflow runs yet.</p>
        ) : null}
      </div>
    </section>
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

function filterDefinitionsByKind(definitions: WorkflowDefinition[], filter: DefinitionFilter): WorkflowDefinition[] {
  if (filter === "scheduled") {
    return definitions.filter((definition) => definition.triggers.length > 0);
  }
  return definitions.filter((definition) => definition.triggers.length === 0);
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
  if (run.name?.trim()) {
    return run.name;
  }
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

function definitionFilterFromParam(value: string | null): DefinitionFilter {
  return value === "scheduled" ? "scheduled" : "manual";
}
