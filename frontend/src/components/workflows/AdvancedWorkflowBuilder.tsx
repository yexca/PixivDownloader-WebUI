import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  Database,
  Filter,
  FolderTree,
  ListChecks,
  Play,
  RotateCcw,
  Save,
  UserRoundSearch
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ToastProvider";
import { createAdvancedWorkflowRun, type AdvancedWorkflowRunRequest } from "@/api/workflows";
import { cn } from "@/lib/utils";

type TriggerMode = "manual" | "schedule";
type TargetScope = "selected" | "all" | "tagged" | "stale";
type SyncMode = "none" | "incremental" | "full";
type CollectMode = "new" | "all_local" | "failed";
type ConflictMode = "skip" | "overwrite" | "rename";
type PreviewTab = "summary" | "json";

type WorkflowDraft = {
  name: string;
  triggerMode: TriggerMode;
  intervalDays: string;
  runAfterStartup: boolean;
  targetScope: TargetScope;
  artistIds: string;
  artistTag: string;
  staleDays: string;
  maxArtists: string;
  syncMode: SyncMode;
  collectMode: CollectMode;
  maxArtworks: string;
  minArtworkId: string;
  maxArtworkId: string;
  filterAi: "include" | "exclude" | "only";
  minBookmarks: string;
  requiredTags: string;
  blockedTags: string;
  downloadEnabled: boolean;
  retryFailed: boolean;
  skipExisting: boolean;
  conflictMode: ConflictMode;
  concurrency: string;
  requestDelay: string;
  namingRule: string;
  stopAboveLimit: boolean;
  stopLimit: string;
  pauseOnLongRun: boolean;
};

type StageKey = "trigger" | "target" | "sync" | "collect" | "filters" | "actions" | "output";

const initialDraft: WorkflowDraft = {
  name: "Artist download pipeline",
  triggerMode: "manual",
  intervalDays: "7",
  runAfterStartup: false,
  targetScope: "selected",
  artistIds: "123456\n234567",
  artistTag: "",
  staleDays: "30",
  maxArtists: "20",
  syncMode: "incremental",
  collectMode: "new",
  maxArtworks: "200",
  minArtworkId: "",
  maxArtworkId: "",
  filterAi: "include",
  minBookmarks: "",
  requiredTags: "",
  blockedTags: "",
  downloadEnabled: true,
  retryFailed: false,
  skipExisting: true,
  conflictMode: "skip",
  concurrency: "1",
  requestDelay: "2",
  namingRule: "{artist}/{title}_{artwork_id}_{page}",
  stopAboveLimit: true,
  stopLimit: "500",
  pauseOnLongRun: false
};

const previewTabs: Array<{ value: PreviewTab; label: string }> = [
  { value: "summary", label: "Summary" },
  { value: "json", label: "JSON" }
];

const stages: Array<{ key: StageKey; title: string; icon: React.ComponentType<{ className?: string }> }> = [
  { key: "trigger", title: "Trigger", icon: CalendarClock },
  { key: "target", title: "Target", icon: UserRoundSearch },
  { key: "sync", title: "Sync", icon: Database },
  { key: "collect", title: "Collect", icon: ListChecks },
  { key: "filters", title: "Filters", icon: Filter },
  { key: "actions", title: "Actions", icon: Play },
  { key: "output", title: "Output", icon: FolderTree }
];

export function AdvancedWorkflowBuilder({ onSubmitted }: { onSubmitted?: () => void }): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [draft, setDraft] = React.useState<WorkflowDraft>(initialDraft);
  const [selectedStage, setSelectedStage] = React.useState<StageKey>("target");
  const [previewTab, setPreviewTab] = React.useState<PreviewTab>("summary");

  const update = <K extends keyof WorkflowDraft>(key: K, value: WorkflowDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const candidateSummary = candidateText(draft);
  const workflowJson = React.useMemo(() => buildAdvancedRequest(draft), [draft]);
  const runMutation = useMutation({
    mutationFn: createAdvancedWorkflowRun,
    onSuccess: (run) => {
      pushToast({ title: "Advanced workflow started", description: run.id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["workflow-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      onSubmitted?.();
    },
    onError: (error) => {
      pushToast({ title: "Advanced workflow failed", description: error.message, tone: "error" });
    }
  });

  return (
    <div className="grid min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-[minmax(0,1fr)_340px]">
      <section className="min-h-0 space-y-4 overflow-y-auto overscroll-contain pr-1">
        <div className="rounded-md border bg-muted/20 p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">Advanced Linear Workflow</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Build the real workflow nodes that the backend will execute.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" onClick={() => setDraft(initialDraft)}>
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              Reset
            </Button>
            <Button
              type="button"
              disabled={runMutation.isPending}
              onClick={() => runMutation.mutate(workflowJson)}
            >
              <Save className="h-4 w-4" aria-hidden="true" />
              Run Workflow
            </Button>
            </div>
          </div>
        </div>
          <div className="surface p-4">
            <div className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)]">
              <aside className="space-y-2">
                {stages.map((stage, index) => (
                  <StageButton
                    key={stage.key}
                    index={index + 1}
                    stage={stage}
                    selected={selectedStage === stage.key}
                    detail={stageDetail(stage.key, draft)}
                    onClick={() => setSelectedStage(stage.key)}
                  />
                ))}
              </aside>

              <div className="min-w-0">
                <StageEditor stage={selectedStage} draft={draft} update={update} />
              </div>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <MetricCard label="Targets" value={targetMetric(draft)} detail={targetDetail(draft)} />
            <MetricCard label="Candidates" value={candidateSummary.value} detail={candidateSummary.detail} />
            <MetricCard label="Action" value={actionMetric(draft)} detail={actionDetail(draft)} />
          </div>
        </section>

        <aside className="min-h-0 space-y-4 overflow-y-auto overscroll-contain pr-1">
          <section className="surface p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">Run Shape</h2>
                <p className="mt-1 text-sm text-muted-foreground">{draft.name || "Untitled workflow"}</p>
              </div>
              <Badge tone={draft.triggerMode === "schedule" ? "warning" : "success"}>
                {draft.triggerMode === "schedule" ? "Scheduled" : "Manual"}
              </Badge>
            </div>

            <div className="mt-4 space-y-3">
              {stages.map((stage, index) => (
                <div key={stage.key} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span className="flex h-7 w-7 items-center justify-center rounded-md border bg-muted text-xs font-semibold">
                      {index + 1}
                    </span>
                    {index < stages.length - 1 ? <span className="h-7 w-px bg-border" /> : null}
                  </div>
                  <div className="min-w-0 pb-2">
                    <div className="flex items-center gap-2">
                      <stage.icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                      <p className="text-sm font-medium">{stage.title}</p>
                    </div>
                    <p className="mt-1 truncate text-xs text-muted-foreground">{stageDetail(stage.key, draft)}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="surface p-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold">Preview</h2>
              <Tabs value={previewTab} onValueChange={setPreviewTab} items={previewTabs} />
            </div>

            {previewTab === "summary" ? (
              <dl className="mt-4 space-y-3 text-sm">
                <PreviewRow label="Trigger" value={triggerDetail(draft)} />
                <PreviewRow label="Target" value={targetDetail(draft)} />
                <PreviewRow label="Sync" value={syncDetail(draft)} />
                <PreviewRow label="Collect" value={collectDetail(draft)} />
                <PreviewRow label="Filters" value={filtersDetail(draft)} />
                <PreviewRow label="Actions" value={actionDetail(draft)} />
                <PreviewRow label="Output" value={outputDetail(draft)} />
              </dl>
            ) : (
              <pre className="mt-4 max-h-[520px] overflow-auto rounded-md border bg-muted/30 p-3 text-xs leading-relaxed">
                {JSON.stringify(workflowJson, null, 2)}
              </pre>
            )}
          </section>
        </aside>
      </div>
  );
}

function StageEditor({
  stage,
  draft,
  update
}: {
  stage: StageKey;
  draft: WorkflowDraft;
  update: <K extends keyof WorkflowDraft>(key: K, value: WorkflowDraft[K]) => void;
}): JSX.Element {
  if (stage === "trigger") {
    return (
      <EditorPanel icon={CalendarClock} title="Trigger" kicker="Schedule">
        <Field label="Workflow name">
          <Input value={draft.name} onChange={(event) => update("name", event.target.value)} />
        </Field>
        <Segmented
          value={draft.triggerMode}
          items={[
            { value: "manual", label: "Manual" },
            { value: "schedule", label: "Schedule" }
          ]}
          onChange={(value) => update("triggerMode", value)}
        />
        {draft.triggerMode === "schedule" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Interval days">
              <Input value={draft.intervalDays} inputMode="numeric" onChange={(event) => update("intervalDays", event.target.value)} />
            </Field>
            <Toggle
              label="Run after startup"
              checked={draft.runAfterStartup}
              onChange={(checked) => update("runAfterStartup", checked)}
            />
          </div>
        ) : null}
      </EditorPanel>
    );
  }

  if (stage === "target") {
    return (
      <EditorPanel icon={UserRoundSearch} title="Target" kicker="Artist range">
        <Field label="Artist scope">
          <Select value={draft.targetScope} onChange={(event) => update("targetScope", event.target.value as TargetScope)} className="w-full">
            <option value="selected">Selected artists</option>
            <option value="all">All local artists</option>
            <option value="tagged">Artists with local tag</option>
            <option value="stale">Artists not checked recently</option>
          </Select>
        </Field>
        {draft.targetScope === "selected" ? (
          <Field label="Artist IDs">
            <Textarea value={draft.artistIds} onChange={(event) => update("artistIds", event.target.value)} />
          </Field>
        ) : null}
        {draft.targetScope === "tagged" ? (
          <Field label="Local tag">
            <Input value={draft.artistTag} onChange={(event) => update("artistTag", event.target.value)} />
          </Field>
        ) : null}
        {draft.targetScope === "stale" ? (
          <Field label="Not checked for days">
            <Input value={draft.staleDays} inputMode="numeric" onChange={(event) => update("staleDays", event.target.value)} />
          </Field>
        ) : null}
        <Field label="Max artists per run">
          <Input value={draft.maxArtists} inputMode="numeric" onChange={(event) => update("maxArtists", event.target.value)} />
        </Field>
      </EditorPanel>
    );
  }

  if (stage === "sync") {
    return (
      <EditorPanel icon={Database} title="Sync" kicker="Local metadata">
        <Segmented
          value={draft.syncMode}
          items={[
            { value: "none", label: "None" },
            { value: "incremental", label: "Incremental" },
            { value: "full", label: "Full rescan" }
          ]}
          onChange={(value) => update("syncMode", value)}
        />
        {draft.syncMode === "full" ? (
          <div className="rounded-md border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning-muted))] p-3 text-sm text-[hsl(var(--warning-foreground))]">
            Full rescan refreshes every target artist before candidate collection.
          </div>
        ) : null}
      </EditorPanel>
    );
  }

  if (stage === "collect") {
    return (
      <EditorPanel icon={ListChecks} title="Collect" kicker="Candidate artworks">
        <Field label="Candidate set">
          <Select value={draft.collectMode} onChange={(event) => update("collectMode", event.target.value as CollectMode)} className="w-full">
            <option value="new">New since last download</option>
            <option value="all_local">All local artworks</option>
            <option value="failed">Failed files only</option>
          </Select>
        </Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Max artworks">
            <Input value={draft.maxArtworks} inputMode="numeric" onChange={(event) => update("maxArtworks", event.target.value)} />
          </Field>
          <Field label="Artwork ID from">
            <Input value={draft.minArtworkId} inputMode="numeric" onChange={(event) => update("minArtworkId", event.target.value)} />
          </Field>
          <Field label="Artwork ID to">
            <Input value={draft.maxArtworkId} inputMode="numeric" onChange={(event) => update("maxArtworkId", event.target.value)} />
          </Field>
        </div>
      </EditorPanel>
    );
  }

  if (stage === "filters") {
    return (
      <EditorPanel icon={Filter} title="Filters" kicker="Candidate rules">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="AI artworks">
            <Select value={draft.filterAi} onChange={(event) => update("filterAi", event.target.value as WorkflowDraft["filterAi"])} className="w-full">
              <option value="include">Include</option>
              <option value="exclude">Exclude</option>
              <option value="only">Only AI</option>
            </Select>
          </Field>
          <Field label="Minimum bookmarks">
            <Input value={draft.minBookmarks} inputMode="numeric" onChange={(event) => update("minBookmarks", event.target.value)} />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Required tags">
            <Input value={draft.requiredTags} onChange={(event) => update("requiredTags", event.target.value)} />
          </Field>
          <Field label="Blocked tags">
            <Input value={draft.blockedTags} onChange={(event) => update("blockedTags", event.target.value)} />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Toggle
            label="Stop above artwork limit"
            checked={draft.stopAboveLimit}
            onChange={(checked) => update("stopAboveLimit", checked)}
          />
          <Field label="Artwork limit">
            <Input value={draft.stopLimit} inputMode="numeric" onChange={(event) => update("stopLimit", event.target.value)} />
          </Field>
        </div>
      </EditorPanel>
    );
  }

  if (stage === "actions") {
    return (
      <EditorPanel icon={Play} title="Actions" kicker="Execution">
        <div className="grid gap-3 sm:grid-cols-2">
          <Toggle label="Download files" checked={draft.downloadEnabled} onChange={(checked) => update("downloadEnabled", checked)} />
          <Toggle label="Retry failed files" checked={draft.retryFailed} onChange={(checked) => update("retryFailed", checked)} />
          <Toggle label="Skip existing files" checked={draft.skipExisting} onChange={(checked) => update("skipExisting", checked)} />
          <Toggle label="Pause on long run" checked={draft.pauseOnLongRun} onChange={(checked) => update("pauseOnLongRun", checked)} />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Conflict mode">
            <Select value={draft.conflictMode} onChange={(event) => update("conflictMode", event.target.value as ConflictMode)} className="w-full">
              <option value="skip">Skip</option>
              <option value="overwrite">Overwrite</option>
              <option value="rename">Rename</option>
            </Select>
          </Field>
          <Field label="Concurrency">
            <Input value={draft.concurrency} inputMode="numeric" onChange={(event) => update("concurrency", event.target.value)} />
          </Field>
          <Field label="Request delay seconds">
            <Input value={draft.requestDelay} inputMode="numeric" onChange={(event) => update("requestDelay", event.target.value)} />
          </Field>
        </div>
      </EditorPanel>
    );
  }

  return (
    <EditorPanel icon={FolderTree} title="Output" kicker="Naming">
      <Field label="Naming rule">
        <Input value={draft.namingRule} onChange={(event) => update("namingRule", event.target.value)} />
      </Field>
      <div className="rounded-md border bg-muted/25 p-3">
        <p className="text-xs font-medium uppercase text-muted-foreground">Preview path</p>
        <p className="mt-2 break-all font-mono text-sm">{previewPath(draft.namingRule)}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {["{artist}", "{artist_id}", "{artwork_id}", "{title}", "{page}", "{original_filename}", "{ext}", "{ai}"].map((token) => (
          <Badge key={token} tone="muted">{token}</Badge>
        ))}
      </div>
    </EditorPanel>
  );
}

function StageButton({
  index,
  stage,
  detail,
  selected,
  onClick
}: {
  index: number;
  stage: { key: StageKey; title: string; icon: React.ComponentType<{ className?: string }> };
  detail: string;
  selected: boolean;
  onClick: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      className={cn(
        "flex min-h-16 w-full items-center gap-3 rounded-md border bg-background p-3 text-left transition-colors hover:bg-muted/60",
        selected && "border-primary bg-primary/5"
      )}
      onClick={onClick}
    >
      <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-md border bg-muted", selected && "border-primary bg-primary/10 text-primary")}>
        <stage.icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2 text-sm font-semibold">
          <span className="text-xs text-muted-foreground">{index}</span>
          {stage.title}
        </span>
        <span className="mt-1 block truncate text-xs text-muted-foreground">{detail}</span>
      </span>
      {selected ? <Check className="h-4 w-4 text-primary" aria-hidden="true" /> : null}
    </button>
  );
}

function EditorPanel({
  icon: Icon,
  title,
  kicker,
  children
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  kicker: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 border-b pb-4">
        <span className="flex h-10 w-10 items-center justify-center rounded-md border bg-muted">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <div>
          <p className="text-xs font-medium uppercase text-muted-foreground">{kicker}</p>
          <h2 className="text-lg font-semibold">{title}</h2>
        </div>
      </div>
      {children}
    </div>
  );
}

function Segmented<T extends string>({
  value,
  items,
  onChange
}: {
  value: T;
  items: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}): JSX.Element {
  return (
    <div className="inline-flex max-w-full flex-wrap gap-1 rounded-md border bg-muted p-1">
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          className={cn(
            "h-8 rounded-sm px-3 text-sm font-medium text-muted-foreground transition-colors",
            value === item.value && "bg-background text-foreground shadow-sm"
          )}
          onClick={() => onChange(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }): JSX.Element {
  return (
    <label className="flex min-h-10 items-center justify-between gap-3 rounded-md border bg-background px-3 py-2 text-sm">
      <span className="font-medium">{label}</span>
      <input className="h-4 w-4 accent-[hsl(var(--primary))]" type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <label className="block text-sm">
      <span className="mb-2 block font-medium">{label}</span>
      {children}
    </label>
  );
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }): JSX.Element {
  return (
    <section className="surface p-4">
      <p className="text-xs font-medium uppercase text-muted-foreground">{label}</p>
      <p className="mt-2 text-xl font-semibold">{value}</p>
      <p className="mt-1 truncate text-sm text-muted-foreground">{detail}</p>
    </section>
  );
}

function PreviewRow({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="grid gap-1 border-b pb-3 last:border-b-0 last:pb-0">
      <dt className="text-xs font-medium uppercase text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function stageDetail(stage: StageKey, draft: WorkflowDraft): string {
  const details: Record<StageKey, string> = {
    trigger: triggerDetail(draft),
    target: targetDetail(draft),
    sync: syncDetail(draft),
    collect: collectDetail(draft),
    filters: filtersDetail(draft),
    actions: actionDetail(draft),
    output: outputDetail(draft)
  };
  return details[stage];
}

function triggerDetail(draft: WorkflowDraft): string {
  return draft.triggerMode === "schedule" ? `Every ${draft.intervalDays || "-"} day(s)` : "Manual run";
}

function targetDetail(draft: WorkflowDraft): string {
  if (draft.targetScope === "selected") {
    return `${countLines(draft.artistIds)} selected artist(s)`;
  }
  if (draft.targetScope === "tagged") {
    return `Artists tagged ${draft.artistTag || "-"}`;
  }
  if (draft.targetScope === "stale") {
    return `Not checked for ${draft.staleDays || "-"} day(s)`;
  }
  return "All local artists";
}

function syncDetail(draft: WorkflowDraft): string {
  if (draft.syncMode === "none") {
    return "Use local database only";
  }
  return draft.syncMode === "full" ? "Full metadata rescan" : "Incremental metadata sync";
}

function collectDetail(draft: WorkflowDraft): string {
  const mode = draft.collectMode === "new" ? "New artworks" : draft.collectMode === "failed" ? "Failed files" : "All local artworks";
  return `${mode}, max ${draft.maxArtworks || "unlimited"}`;
}

function filtersDetail(draft: WorkflowDraft): string {
  const parts = [];
  if (draft.filterAi !== "include") {
    parts.push(draft.filterAi === "exclude" ? "exclude AI" : "AI only");
  }
  if (draft.minBookmarks) {
    parts.push(`${draft.minBookmarks}+ bookmarks`);
  }
  if (draft.requiredTags) {
    parts.push(`require ${draft.requiredTags}`);
  }
  if (draft.blockedTags) {
    parts.push(`block ${draft.blockedTags}`);
  }
  return parts.length ? parts.join(", ") : "No metadata filters";
}

function actionDetail(draft: WorkflowDraft): string {
  const actions = [];
  if (draft.downloadEnabled) {
    actions.push("download");
  }
  if (draft.retryFailed) {
    actions.push("retry failed");
  }
  return `${actions.join(" + ") || "no action"}, ${draft.conflictMode} conflicts`;
}

function outputDetail(draft: WorkflowDraft): string {
  return draft.namingRule || "Default naming";
}

function targetMetric(draft: WorkflowDraft): string {
  if (draft.targetScope === "selected") {
    return String(countLines(draft.artistIds));
  }
  return draft.maxArtists || "-";
}

function candidateText(draft: WorkflowDraft): { value: string; detail: string } {
  return {
    value: draft.maxArtworks || "-",
    detail: collectDetail(draft)
  };
}

function actionMetric(draft: WorkflowDraft): string {
  if (draft.downloadEnabled && draft.retryFailed) {
    return "Download + Retry";
  }
  if (draft.retryFailed) {
    return "Retry";
  }
  return draft.downloadEnabled ? "Download" : "None";
}

function previewPath(rule: string): string {
  return (rule || "{artist}/{original_filename}")
    .replaceAll("{artist}", "Artist")
    .replaceAll("{artist_id}", "123456")
    .replaceAll("{artwork_id}", "987654321")
    .replaceAll("{title}", "Artwork title")
    .replaceAll("{page}", "0")
    .replaceAll("{original_filename}", "987654321_p0.jpg")
    .replaceAll("{ext}", "jpg")
    .replaceAll("{ai}", "non-AI");
}

function buildAdvancedRequest(draft: WorkflowDraft): AdvancedWorkflowRunRequest {
  return {
    definition: {
      name: draft.name,
      nodes: [
      {
        id: "target",
        type: "artist_target",
        title: "Target artists",
        config: {
        scope: draft.targetScope,
        artist_ids: draft.targetScope === "selected" ? lines(draft.artistIds) : [],
        tag: draft.targetScope === "tagged" ? draft.artistTag : null,
        stale_days: draft.targetScope === "stale" ? numberOrNull(draft.staleDays) : null,
          max_artists: numberOrNull(draft.maxArtists)
        }
      },
      {
        id: "sync",
        type: "sync_metadata",
        title: "Sync metadata",
        config: {
        mode: draft.syncMode
        }
      },
      {
        id: "collect",
        type: "collect_artworks",
        title: "Collect candidates",
        config: {
        mode: draft.collectMode,
        max_artworks: numberOrNull(draft.maxArtworks),
        min_artwork_id: draft.minArtworkId || null,
        max_artwork_id: draft.maxArtworkId || null
        }
      },
      {
        id: "filters",
        type: "filter_artworks",
        title: "Filter candidates",
        config: {
        ai: draft.filterAi,
        min_bookmarks: numberOrNull(draft.minBookmarks),
        required_tags: commaList(draft.requiredTags),
        blocked_tags: commaList(draft.blockedTags),
        stop_above_limit: draft.stopAboveLimit ? numberOrNull(draft.stopLimit) : null
        }
      },
      {
        id: "actions",
        type: "execute_actions",
        title: "Execute actions",
        config: {
          actions: actionList(draft),
        download: draft.downloadEnabled,
        retry_failed: draft.retryFailed,
        skip_existing: draft.skipExisting,
        conflict_mode: draft.conflictMode,
        concurrency: numberOrNull(draft.concurrency),
        request_delay_seconds: numberOrNull(draft.requestDelay),
          pause_on_long_run: draft.pauseOnLongRun,
          naming_rule: draft.namingRule
        }
      },
      {
        id: "output",
        type: "file_output",
        title: "Output",
        config: {
        naming_rule: draft.namingRule
        }
      }
      ]
    }
  };
}

function actionList(draft: WorkflowDraft): string[] {
  const actions: string[] = [];
  if (draft.syncMode !== "none") {
    actions.push("sync_artist");
  }
  if (draft.downloadEnabled) {
    actions.push("download_artist");
  }
  if (draft.retryFailed) {
    actions.push("retry_failed_artist");
  }
  return actions.length ? actions : ["download_artist"];
}

function countLines(value: string): number {
  return lines(value).length;
}

function lines(value: string): string[] {
  return value.split(/[\n,\s]+/).map((item) => item.trim()).filter(Boolean);
}

function commaList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function numberOrNull(value: string): number | null {
  const text = value.trim();
  return text ? Number(text) : null;
}
