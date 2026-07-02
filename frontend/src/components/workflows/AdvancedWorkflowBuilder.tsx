import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  Database,
  Filter,
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
import {
  createAdvancedWorkflowRun,
  saveWorkflowDefinition,
  type AdvancedWorkflowNode,
  type AdvancedWorkflowRunRequest,
  type WorkflowDefinition,
  type WorkflowScheduleRule
} from "@/api/workflows";
import { cn } from "@/lib/utils";

type TriggerMode = "manual" | "schedule";
type SaveIntent = "run_now" | "save_only" | "save_and_schedule" | "run_and_schedule";
type ScheduleType = "interval" | "daily" | "weekly" | "monthly";
type IntervalUnit = "minutes" | "hours" | "days";
type TargetScope = "selected" | "all" | "tagged" | "stale";
type SyncMode = "none" | "incremental" | "full";
type CollectMode =
  | "new_since_last_download"
  | "pending_files"
  | "all_synced"
  | "failed_files";
type CollectLimitMode = "none" | "limit";
type CollectSortOrder = "newest_first" | "oldest_first" | "local_order";
type ConflictMode = "skip" | "overwrite" | "rename";
type ExecutionUnit = "artist" | "set";
type PreviewTab = "summary" | "json";

type WorkflowDraft = {
  name: string;
  modules: {
    sync: boolean;
    collect: boolean;
    filters: boolean;
    actions: boolean;
  };
  triggerMode: TriggerMode;
  saveIntent: SaveIntent;
  scheduleType: ScheduleType;
  intervalEvery: string;
  intervalUnit: IntervalUnit;
  scheduleTime: string;
  weeklyDays: number[];
  monthlyDay: string;
  targetScope: TargetScope;
  artistIds: string;
  artistTag: string;
  staleDays: string;
  maxArtists: string;
  syncMode: SyncMode;
  collectMode: CollectMode;
  collectLimitMode: CollectLimitMode;
  maxArtworks: string;
  minArtworkId: string;
  maxArtworkId: string;
  collectSortOrder: CollectSortOrder;
  filterAi: "include" | "exclude" | "only";
  requiredTags: string;
  blockedTags: string;
  downloadEnabled: boolean;
  conflictMode: ConflictMode;
  executionUnit: ExecutionUnit;
  namingRule: string;
  stopAboveLimit: boolean;
  stopLimit: string;
};

export type AdvancedWorkflowBuilderStage = "trigger" | "target" | "sync" | "collect" | "filters" | "actions";
type StageKey = AdvancedWorkflowBuilderStage;

const initialDraft: WorkflowDraft = {
  name: "Artist download pipeline",
  modules: {
    sync: true,
    collect: true,
    filters: true,
    actions: true
  },
  triggerMode: "manual",
  saveIntent: "run_now",
  scheduleType: "interval",
  intervalEvery: "6",
  intervalUnit: "hours",
  scheduleTime: "03:00",
  weeklyDays: [1, 3, 5],
  monthlyDay: "1",
  targetScope: "selected",
  artistIds: "123456\n234567",
  artistTag: "",
  staleDays: "30",
  maxArtists: "20",
  syncMode: "incremental",
  collectMode: "new_since_last_download",
  collectLimitMode: "limit",
  maxArtworks: "200",
  minArtworkId: "",
  maxArtworkId: "",
  collectSortOrder: "newest_first",
  filterAi: "include",
  requiredTags: "",
  blockedTags: "",
  downloadEnabled: true,
  conflictMode: "skip",
  executionUnit: "artist",
  namingRule: "{artist}/{title}_{artwork_id}_{page}",
  stopAboveLimit: true,
  stopLimit: "500"
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
  { key: "actions", title: "Actions", icon: Play }
];

type AdvancedWorkflowBuilderProps = {
  definition?: WorkflowDefinition | null;
  initialStage?: AdvancedWorkflowBuilderStage;
  triggerId?: number | null;
  onSubmitted?: () => void;
};

export function AdvancedWorkflowBuilder({
  definition,
  initialStage = "target",
  triggerId,
  onSubmitted
}: AdvancedWorkflowBuilderProps): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const hydratedDraft = React.useMemo(() => draftFromDefinition(definition), [definition]);
  const [draft, setDraft] = React.useState<WorkflowDraft>(hydratedDraft);
  const [selectedStage, setSelectedStage] = React.useState<StageKey>(initialStage);
  const [previewTab, setPreviewTab] = React.useState<PreviewTab>("summary");

  React.useEffect(() => {
    setDraft(hydratedDraft);
    setSelectedStage(initialStage);
  }, [hydratedDraft, initialStage]);

  const update = <K extends keyof WorkflowDraft>(key: K, value: WorkflowDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };
  const updateModule = (module: keyof WorkflowDraft["modules"], enabled: boolean) => {
    setDraft((current) => {
      const modules = { ...current.modules, [module]: enabled };
      if (module === "collect" && !enabled) {
        modules.filters = false;
        modules.actions = false;
      }
      if ((module === "filters" || module === "actions") && enabled) {
        modules.collect = true;
      }
      if (module === "sync" && !enabled && selectedStage === "sync") {
        setSelectedStage("target");
      }
      if (module === "collect" && !enabled && selectedStage === "collect") {
        setSelectedStage("target");
      }
      if (module === "filters" && !enabled && selectedStage === "filters") {
        setSelectedStage("target");
      }
      if (module === "actions" && !enabled && selectedStage === "actions") {
        setSelectedStage("target");
      }
      return { ...current, modules };
    });
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
  const saveMutation = useMutation({
    mutationFn: saveWorkflowDefinition,
    onSuccess: (response) => {
      const runId = response.run?.id;
      const triggerLabel = response.trigger ? " with trigger" : "";
      pushToast({
        title: runId ? "Workflow saved and started" : `Workflow saved${triggerLabel}`,
        description: runId ?? response.definition.id,
        tone: "success"
      });
      void queryClient.invalidateQueries({ queryKey: ["workflow-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["workflow-definitions"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      onSubmitted?.();
    },
    onError: (error) => {
      pushToast({ title: "Workflow could not be saved", description: error.message, tone: "error" });
    }
  });

  const submitting = runMutation.isPending || saveMutation.isPending;
  const submitAdvanced = () => {
    if (!definition && draft.saveIntent === "run_now") {
      runMutation.mutate(workflowJson);
      return;
    }
    const shouldSchedule = draft.saveIntent === "save_and_schedule" || draft.saveIntent === "run_and_schedule";
    saveMutation.mutate({
      definition_id: definition?.id ?? null,
      definition: workflowJson.definition,
      trigger: shouldSchedule
        ? {
            trigger_id: triggerId ?? definition?.triggers[0]?.id ?? null,
            enabled: true,
            schedule: buildScheduleRule(draft),
            run_now: draft.saveIntent === "run_and_schedule"
          }
        : null
    });
  };

  return (
    <div className="grid min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-[minmax(0,1fr)_340px]">
      <section className="min-h-0 space-y-4 overflow-y-auto overscroll-contain pr-1">
        <div className="rounded-md border bg-muted/20 p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">
                {definition ? "Edit Workflow Definition" : "Advanced Linear Workflow"}
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Build the real workflow nodes that the backend will execute.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" onClick={() => setDraft(hydratedDraft)}>
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              Reset
            </Button>
            <Button
              type="button"
              disabled={submitting}
              onClick={submitAdvanced}
            >
              <Save className="h-4 w-4" aria-hidden="true" />
              {submitLabel(draft)}
            </Button>
            </div>
          </div>
          <ModuleSwitches draft={draft} onChange={updateModule} />
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
                    enabled={stageEnabled(stage.key, draft)}
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
                stageEnabled(stage.key, draft) ? (
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
                ) : null
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
                {draft.modules.sync ? <PreviewRow label="Sync" value={syncDetail(draft)} /> : null}
                {draft.modules.collect ? <PreviewRow label="Collect" value={collectDetail(draft)} /> : null}
                {draft.modules.filters ? <PreviewRow label="Filters" value={filtersDetail(draft)} /> : null}
                {draft.modules.actions ? <PreviewRow label="Actions" value={actionDetail(draft)} /> : null}
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
          onChange={(value) => {
            update("triggerMode", value);
            update("saveIntent", value === "manual" ? "run_now" : "save_and_schedule");
          }}
        />
        {draft.triggerMode === "schedule" ? (
          <div className="space-y-4">
            <Field label="On save">
              <Segmented
                value={draft.saveIntent}
                items={[
                  { value: "save_and_schedule", label: "Save schedule" },
                  { value: "run_and_schedule", label: "Run + schedule" },
                  { value: "save_only", label: "Save only" }
                ]}
                onChange={(value) => update("saveIntent", value)}
              />
            </Field>
            <Field label="Schedule type">
              <Select value={draft.scheduleType} onChange={(event) => update("scheduleType", event.target.value as ScheduleType)} className="w-full">
                <option value="interval">Interval</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </Select>
            </Field>
            {draft.scheduleType === "interval" ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Every">
                  <Input value={draft.intervalEvery} inputMode="numeric" onChange={(event) => update("intervalEvery", event.target.value)} />
                </Field>
                <Field label="Unit">
                  <Select value={draft.intervalUnit} onChange={(event) => update("intervalUnit", event.target.value as IntervalUnit)} className="w-full">
                    <option value="minutes">Minutes</option>
                    <option value="hours">Hours</option>
                    <option value="days">Days</option>
                  </Select>
                </Field>
              </div>
            ) : null}
            {draft.scheduleType === "daily" ? (
              <Field label="Time">
                <Input value={draft.scheduleTime} type="time" onChange={(event) => update("scheduleTime", event.target.value)} />
              </Field>
            ) : null}
            {draft.scheduleType === "weekly" ? (
              <div className="space-y-3">
                <Field label="Days">
                  <WeekdayPicker value={draft.weeklyDays} onChange={(value) => update("weeklyDays", value)} />
                </Field>
                <Field label="Time">
                  <Input value={draft.scheduleTime} type="time" onChange={(event) => update("scheduleTime", event.target.value)} />
                </Field>
              </div>
            ) : null}
            {draft.scheduleType === "monthly" ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Day">
                  <Select value={draft.monthlyDay} onChange={(event) => update("monthlyDay", event.target.value)} className="w-full">
                    {Array.from({ length: 31 }, (_, index) => String(index + 1)).map((day) => (
                      <option key={day} value={day}>{day}</option>
                    ))}
                    <option value="last">Last day</option>
                  </Select>
                </Field>
                <Field label="Time">
                  <Input value={draft.scheduleTime} type="time" onChange={(event) => update("scheduleTime", event.target.value)} />
                </Field>
              </div>
            ) : null}
          </div>
        ) : (
          <Field label="On submit">
            <Segmented
              value={draft.saveIntent}
              items={[
                { value: "run_now", label: "Run now" },
                { value: "save_only", label: "Save only" }
              ]}
              onChange={(value) => update("saveIntent", value)}
            />
          </Field>
        )}
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
            <option value="new_since_last_download">New since last download</option>
            <option value="pending_files">Pending files</option>
            <option value="all_synced">All synced artworks</option>
            <option value="failed_files">Failed files</option>
          </Select>
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Candidate limit">
            <div className="flex flex-wrap gap-2">
              <Segmented
                value={draft.collectLimitMode}
                items={[
                  { value: "none", label: "No limit" },
                  { value: "limit", label: "Limit" }
                ]}
                onChange={(value) => update("collectLimitMode", value)}
              />
              {draft.collectLimitMode === "limit" ? (
                <Input
                  value={draft.maxArtworks}
                  inputMode="numeric"
                  className="w-28"
                  onChange={(event) => update("maxArtworks", event.target.value)}
                />
              ) : null}
            </div>
          </Field>
          <Field label="Sort">
            <Select
              value={draft.collectSortOrder}
              onChange={(event) => update("collectSortOrder", event.target.value as CollectSortOrder)}
              className="w-full"
            >
              <option value="newest_first">Newest first</option>
              <option value="oldest_first">Oldest first</option>
              <option value="local_order">Local order</option>
            </Select>
          </Field>
        </div>
        <Field label="Artwork ID range">
          <div className="flex items-center gap-2">
            <Input
              value={draft.minArtworkId}
              inputMode="numeric"
              placeholder="from"
              onChange={(event) => update("minArtworkId", event.target.value)}
            />
            <span className="text-sm text-muted-foreground">~</span>
            <Input
              value={draft.maxArtworkId}
              inputMode="numeric"
              placeholder="to"
              onChange={(event) => update("maxArtworkId", event.target.value)}
            />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Empty means no limit.
          </p>
          </Field>
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
          <Field label="Required tags">
            <Input value={draft.requiredTags} onChange={(event) => update("requiredTags", event.target.value)} />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
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
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Execution unit">
            <Segmented
              value={draft.executionUnit}
              items={[
                { value: "artist", label: "Per artist" },
                { value: "set", label: "Whole set" }
              ]}
              onChange={(value) => update("executionUnit", value)}
            />
          </Field>
          <Field label="Conflict mode">
            <Select value={draft.conflictMode} onChange={(event) => update("conflictMode", event.target.value as ConflictMode)} className="w-full">
              <option value="skip">Skip</option>
              <option value="overwrite">Overwrite</option>
              <option value="rename">Rename</option>
            </Select>
          </Field>
        </div>
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
}

function StageButton({
  index,
  stage,
  detail,
  selected,
  enabled,
  onClick
}: {
  index: number;
  stage: { key: StageKey; title: string; icon: React.ComponentType<{ className?: string }> };
  detail: string;
  selected: boolean;
  enabled: boolean;
  onClick: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      className={cn(
        "flex min-h-16 w-full items-center gap-3 rounded-md border bg-background p-3 text-left transition-colors hover:bg-muted/60",
        selected && "border-primary bg-primary/5",
        !enabled && "opacity-50"
      )}
      disabled={!enabled}
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

function ModuleSwitches({
  draft,
  onChange
}: {
  draft: WorkflowDraft;
  onChange: (module: keyof WorkflowDraft["modules"], enabled: boolean) => void;
}): JSX.Element {
  const items: Array<{ key: keyof WorkflowDraft["modules"]; label: string; detail: string }> = [
    { key: "sync", label: "Sync", detail: "Refresh Pixiv metadata" },
    { key: "collect", label: "Collect", detail: "Build artwork candidates" },
    { key: "filters", label: "Filters", detail: "Prune candidates" },
    { key: "actions", label: "Actions", detail: "Download or retry files" }
  ];
  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <label key={item.key} className="flex min-h-14 items-center justify-between gap-3 rounded-md border bg-background px-3 py-2 text-sm">
          <span className="min-w-0">
            <span className="block font-medium">{item.label}</span>
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">{item.detail}</span>
          </span>
          <input
            type="checkbox"
            className="h-4 w-4 shrink-0 accent-[hsl(var(--primary))]"
            checked={draft.modules[item.key]}
            disabled={(item.key === "filters" || item.key === "actions") && !draft.modules.collect}
            onChange={(event) => onChange(item.key, event.target.checked)}
          />
        </label>
      ))}
    </div>
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

function WeekdayPicker({ value, onChange }: { value: number[]; onChange: (value: number[]) => void }): JSX.Element {
  const days = [
    { value: 1, label: "Mon" },
    { value: 2, label: "Tue" },
    { value: 3, label: "Wed" },
    { value: 4, label: "Thu" },
    { value: 5, label: "Fri" },
    { value: 6, label: "Sat" },
    { value: 7, label: "Sun" }
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {days.map((day) => {
        const selected = value.includes(day.value);
        return (
          <button
            key={day.value}
            type="button"
            className={cn(
              "h-8 rounded-md border px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted",
              selected && "border-primary bg-primary/10 text-primary"
            )}
            onClick={() => {
              const next = selected
                ? value.filter((item) => item !== day.value)
                : [...value, day.value].sort((left, right) => left - right);
              onChange(next.length ? next : [day.value]);
            }}
          >
            {day.label}
          </button>
        );
      })}
    </div>
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
    actions: actionDetail(draft)
  };
  return details[stage];
}

function stageEnabled(stage: StageKey, draft: WorkflowDraft): boolean {
  if (stage === "trigger" || stage === "target") {
    return true;
  }
  return draft.modules[stage];
}

function triggerDetail(draft: WorkflowDraft): string {
  if (draft.triggerMode !== "schedule") {
    return draft.saveIntent === "save_only" ? "Saved definition" : "Manual run";
  }
  return `${scheduleRuleText(draft)}, ${saveIntentText(draft.saveIntent)}`;
}

function submitLabel(draft: WorkflowDraft): string {
  const labels: Record<SaveIntent, string> = {
    run_now: "Run Workflow",
    save_only: "Save Workflow",
    save_and_schedule: "Save Schedule",
    run_and_schedule: "Run + Schedule"
  };
  return labels[draft.saveIntent];
}

function saveIntentText(intent: SaveIntent): string {
  const labels: Record<SaveIntent, string> = {
    run_now: "run now",
    save_only: "save only",
    save_and_schedule: "scheduled",
    run_and_schedule: "run now and schedule"
  };
  return labels[intent];
}

function scheduleRuleText(draft: WorkflowDraft): string {
  if (draft.scheduleType === "daily") {
    return `Daily at ${draft.scheduleTime || "--:--"}`;
  }
  if (draft.scheduleType === "weekly") {
    return `Weekly at ${draft.scheduleTime || "--:--"}`;
  }
  if (draft.scheduleType === "monthly") {
    return `Monthly day ${draft.monthlyDay || "-"} at ${draft.scheduleTime || "--:--"}`;
  }
  return `Every ${draft.intervalEvery || "-"} ${draft.intervalUnit}`;
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
  if (!draft.modules.sync) {
    return "Disabled";
  }
  if (draft.syncMode === "none") {
    return "Use local database only";
  }
  return draft.syncMode === "full" ? "Full metadata rescan" : "Incremental metadata sync";
}

function collectDetail(draft: WorkflowDraft): string {
  if (!draft.modules.collect) {
    return "Disabled";
  }
  const modes: Record<CollectMode, string> = {
    new_since_last_download: "New since last download",
    pending_files: "Pending files",
    all_synced: "All synced artworks",
    failed_files: "Failed files"
  };
  const limit = draft.collectLimitMode === "limit" ? draft.maxArtworks || "-" : "unlimited";
  return `${modes[draft.collectMode]}, ${limit}`;
}

function filtersDetail(draft: WorkflowDraft): string {
  if (!draft.modules.filters) {
    return "Disabled";
  }
  const parts = [];
  if (draft.filterAi !== "include") {
    parts.push(draft.filterAi === "exclude" ? "exclude AI" : "AI only");
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
  if (!draft.modules.actions) {
    return "Disabled";
  }
  const unit = draft.executionUnit === "artist" ? "per artist" : "whole set";
  const naming = draft.namingRule ? "custom naming" : "default naming";
  return `${draft.downloadEnabled ? "download" : "no action"}, ${unit}, ${draft.conflictMode}, ${naming}`;
}

function targetMetric(draft: WorkflowDraft): string {
  if (draft.targetScope === "selected") {
    return String(countLines(draft.artistIds));
  }
  return draft.maxArtists || "-";
}

function candidateText(draft: WorkflowDraft): { value: string; detail: string } {
  if (!draft.modules.collect) {
    return { value: "-", detail: "Candidate collection disabled" };
  }
  return {
    value: draft.collectLimitMode === "limit" ? draft.maxArtworks || "-" : "All",
    detail: collectDetail(draft)
  };
}

function actionMetric(draft: WorkflowDraft): string {
  if (!draft.modules.actions) {
    return "None";
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
  const nodes: AdvancedWorkflowRunRequest["definition"]["nodes"] = [
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
    }
  ];
  if (draft.modules.sync && draft.syncMode !== "none") {
    nodes.push({
      id: "sync",
      type: "sync_metadata",
      title: "Sync metadata",
      config: {
        mode: draft.syncMode
      }
    });
  }
  if (draft.modules.collect) {
    nodes.push({
      id: "collect",
      type: "collect_artworks",
      title: "Collect candidates",
      config: {
        mode: draft.collectMode,
        max_artworks: draft.collectLimitMode === "limit" ? numberOrNull(draft.maxArtworks) : null,
        min_artwork_id: draft.minArtworkId || null,
        max_artwork_id: draft.maxArtworkId || null,
        sort_order: draft.collectSortOrder
      }
    });
  }
  if (draft.modules.filters) {
    nodes.push({
      id: "filters",
      type: "filter_artworks",
      title: "Filter candidates",
      config: {
        ai: draft.filterAi,
        required_tags: commaList(draft.requiredTags),
        blocked_tags: commaList(draft.blockedTags),
        stop_above_limit: draft.stopAboveLimit ? numberOrNull(draft.stopLimit) : null
      }
    });
  }
  if (draft.modules.actions) {
    nodes.push({
      id: "actions",
      type: "execute_actions",
      title: "Execute actions",
      config: {
        download: draft.downloadEnabled,
        execution_unit: draft.executionUnit,
        conflict_mode: draft.conflictMode,
        naming_rule: draft.namingRule
      }
    });
  }
  return {
    definition: {
      name: draft.name,
      nodes
    }
  };
}

function buildScheduleRule(draft: WorkflowDraft): WorkflowScheduleRule {
  if (draft.scheduleType === "daily") {
    return { type: "daily", time: draft.scheduleTime || "00:00" };
  }
  if (draft.scheduleType === "weekly") {
    return {
      type: "weekly",
      days_of_week: draft.weeklyDays.length ? draft.weeklyDays : [1],
      time: draft.scheduleTime || "00:00"
    };
  }
  if (draft.scheduleType === "monthly") {
    return {
      type: "monthly",
      day: draft.monthlyDay === "last" ? "last" : Math.max(1, Number(draft.monthlyDay) || 1),
      time: draft.scheduleTime || "00:00"
    };
  }
  return {
    type: "interval",
    every: Math.max(1, Number(draft.intervalEvery) || 1),
    unit: draft.intervalUnit
  };
}

function draftFromDefinition(definition?: WorkflowDefinition | null): WorkflowDraft {
  if (!definition) {
    return initialDraft;
  }
  const nodes = workflowNodesFromDefinition(definition);
  const scheduleDraft = scheduleDraftFromTrigger(definition.triggers[0]?.schedule);
  const target = findNode(nodes, "artist_target");
  const sync = findNode(nodes, "sync_metadata");
  const collect = findNode(nodes, "collect_artworks");
  const filters = findNode(nodes, "filter_artworks");
  const actions = findNode(nodes, "execute_actions");
  const targetConfig = target?.config ?? {};
  const syncConfig = sync?.config ?? {};
  const collectConfig = collect?.config ?? {};
  const filterConfig = filters?.config ?? {};
  const actionConfig = actions?.config ?? {};
  const scope = stringOption(targetConfig.scope, initialDraft.targetScope) as TargetScope;
  const maxArtworks = collectConfig.max_artworks;
  return {
    ...initialDraft,
    ...scheduleDraft,
    name: definition.name,
    triggerMode: definition.triggers.length ? "schedule" : "manual",
    saveIntent: definition.triggers.length ? "save_and_schedule" : "save_only",
    modules: {
      sync: Boolean(sync),
      collect: Boolean(collect),
      filters: Boolean(filters),
      actions: Boolean(actions)
    },
    targetScope: isTargetScope(scope) ? scope : initialDraft.targetScope,
    artistIds: arrayText(targetConfig.artist_ids),
    artistTag: stringOption(targetConfig.tag, ""),
    staleDays: numberText(targetConfig.stale_days),
    maxArtists: numberText(targetConfig.max_artists) || initialDraft.maxArtists,
    syncMode: sync ? syncModeOption(syncConfig.mode) : initialDraft.syncMode,
    collectMode: collectModeOption(collectConfig.mode),
    collectLimitMode: maxArtworks === null || maxArtworks === undefined || maxArtworks === "" ? "none" : "limit",
    maxArtworks: numberText(maxArtworks),
    minArtworkId: stringOption(collectConfig.min_artwork_id, ""),
    maxArtworkId: stringOption(collectConfig.max_artwork_id, ""),
    collectSortOrder: collectSortOption(collectConfig.sort_order),
    filterAi: filterAiOption(filterConfig.ai),
    requiredTags: arrayText(filterConfig.required_tags, ", "),
    blockedTags: arrayText(filterConfig.blocked_tags, ", "),
    stopAboveLimit: filterConfig.stop_above_limit !== null && filterConfig.stop_above_limit !== undefined,
    stopLimit: numberText(filterConfig.stop_above_limit) || initialDraft.stopLimit,
    downloadEnabled: Boolean(actionConfig.download ?? initialDraft.downloadEnabled),
    executionUnit: executionUnitOption(actionConfig.execution_unit),
    conflictMode: conflictModeOption(actionConfig.conflict_mode),
    namingRule: stringOption(actionConfig.naming_rule, initialDraft.namingRule)
  };
}

function scheduleDraftFromTrigger(schedule?: Record<string, unknown>): Partial<WorkflowDraft> {
  if (!schedule) {
    return {};
  }
  const type = scheduleTypeOption(schedule.type);
  if (type === "daily") {
    return {
      scheduleType: "daily",
      scheduleTime: stringOption(schedule.time, initialDraft.scheduleTime)
    };
  }
  if (type === "weekly") {
    return {
      scheduleType: "weekly",
      scheduleTime: stringOption(schedule.time, initialDraft.scheduleTime),
      weeklyDays: numberArray(schedule.days_of_week, initialDraft.weeklyDays)
    };
  }
  if (type === "monthly") {
    const day = schedule.day;
    return {
      scheduleType: "monthly",
      scheduleTime: stringOption(schedule.time, initialDraft.scheduleTime),
      monthlyDay: day === "last" ? "last" : numberText(day) || initialDraft.monthlyDay
    };
  }
  return {
    scheduleType: "interval",
    intervalEvery: numberText(schedule.every) || initialDraft.intervalEvery,
    intervalUnit: intervalUnitOption(schedule.unit)
  };
}

function workflowNodesFromDefinition(definition: WorkflowDefinition): AdvancedWorkflowNode[] {
  const nodes = (definition.definition as { nodes?: unknown }).nodes;
  if (!Array.isArray(nodes)) {
    return [];
  }
  return nodes.filter(isAdvancedWorkflowNode);
}

function isAdvancedWorkflowNode(value: unknown): value is AdvancedWorkflowNode {
  if (!value || typeof value !== "object") {
    return false;
  }
  const node = value as Partial<AdvancedWorkflowNode>;
  return typeof node.id === "string" && typeof node.type === "string" && typeof node.config === "object";
}

function findNode(nodes: AdvancedWorkflowNode[], type: AdvancedWorkflowNode["type"]): AdvancedWorkflowNode | undefined {
  return nodes.find((node) => node.type === type);
}

function isTargetScope(value: string): value is TargetScope {
  return value === "selected" || value === "all" || value === "tagged" || value === "stale";
}

function syncModeOption(value: unknown): SyncMode {
  return value === "full" || value === "incremental" || value === "none" ? value : initialDraft.syncMode;
}

function collectModeOption(value: unknown): CollectMode {
  if (value === "pending_files" || value === "all_synced" || value === "failed_files" || value === "new_since_last_download") {
    return value;
  }
  return initialDraft.collectMode;
}

function collectSortOption(value: unknown): CollectSortOrder {
  if (value === "oldest_first" || value === "local_order" || value === "newest_first") {
    return value;
  }
  return initialDraft.collectSortOrder;
}

function filterAiOption(value: unknown): WorkflowDraft["filterAi"] {
  if (value === "exclude" || value === "only" || value === "include") {
    return value;
  }
  return initialDraft.filterAi;
}

function executionUnitOption(value: unknown): ExecutionUnit {
  if (value === "set" || value === "artist") {
    return value;
  }
  return initialDraft.executionUnit;
}

function scheduleTypeOption(value: unknown): ScheduleType {
  if (value === "daily" || value === "weekly" || value === "monthly" || value === "interval") {
    return value;
  }
  return initialDraft.scheduleType;
}

function intervalUnitOption(value: unknown): IntervalUnit {
  if (value === "minutes" || value === "hours" || value === "days") {
    return value;
  }
  return initialDraft.intervalUnit;
}

function conflictModeOption(value: unknown): ConflictMode {
  if (value === "overwrite" || value === "rename" || value === "skip") {
    return value;
  }
  return initialDraft.conflictMode;
}

function stringOption(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function numberText(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return typeof value === "string" ? value : "";
}

function arrayText(value: unknown, separator = "\n"): string {
  if (!Array.isArray(value)) {
    return "";
  }
  return value.map((item) => String(item)).filter(Boolean).join(separator);
}

function numberArray(value: unknown, fallback: number[]): number[] {
  if (!Array.isArray(value)) {
    return fallback;
  }
  const parsed = value.map((item) => Number(item)).filter((item) => Number.isInteger(item) && item >= 1 && item <= 7);
  return parsed.length ? parsed : fallback;
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
