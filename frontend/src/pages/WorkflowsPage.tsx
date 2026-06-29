import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  CheckCircle2,
  Copy,
  ListPlus,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Wand2,
  XCircle
} from "lucide-react";

import { createArtist, listLocalTags, type LocalTag } from "@/api/artists";
import { createDownloadJob } from "@/api/downloads";
import { getJob, listJobs, type Job, type JobDetail } from "@/api/jobs";
import { getSettings, updateSettings, type SettingsResponse } from "@/api/settings";
import {
  createScheduledTask,
  deleteScheduledTask,
  listScheduledTasks,
  runScheduledTask,
  type ScheduledTask,
  type ScheduledTaskAction,
  type ScheduledTaskArtistSelection,
  type ScheduledTaskConfig,
  type ScheduledTaskTargetType,
  updateScheduledTask
} from "@/api/scheduledTasks";
import {
  createWorkflowRun,
  listWorkflowRuns,
  runWorkflow,
  type WorkflowBatchRun,
  type WorkflowBatchRunItem
} from "@/api/workflows";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs } from "@/components/ui/tabs";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { useToast } from "@/components/ToastProvider";
import { cn, formatDate } from "@/lib/utils";

type WorkflowStatusTab = "active" | "failed" | "completed";
type ArchiveFilter = "normal" | "include" | "archived";
type ModuleKey = "schedule" | "target" | "filters" | "actions" | "options" | "naming" | "rule";
type WorkflowTarget =
  | "artists"
  | "artworks"
  | "single_artist"
  | "single_artwork"
  | "all_artists"
  | "artists_with_tag"
  | "artists_not_checked";
type WorkflowAction = "download_artist" | "sync_artist" | "retry_failed_artist";
type DownloadScope = "incremental" | "full";
type TagVariantBehavior = "download" | "skip" | "retry_failed";
type ArtistTargetSource = "artist_ids" | "artwork_ids";

type RuleConfig = {
  only_new_artworks: boolean;
  stop_if_artwork_count_above: boolean;
  artwork_count_limit: string;
  skip_if_last_run_failed: boolean;
  tag_variant_enabled: boolean;
  tag_variant_tag: string;
  tag_variant_behavior: TagVariantBehavior;
  tag_variant_naming_rule: string;
};

type WorkflowForm = {
  name: string;
  modules: Record<ModuleKey, boolean>;
  interval_days: number;
  enabled: boolean;
  run_after_startup: boolean;
  target_type: WorkflowTarget;
  artist_id: string;
  artwork_id: string;
  artist_ids: string[];
  artist_id_input: string;
  artwork_ids: string[];
  artwork_id_input: string;
  artist_source: ArtistTargetSource;
  tags: string[];
  stale_target_days: number;
  max_artists_per_run: number;
  artist_selection: ScheduledTaskArtistSelection;
  skip_unavailable_artists: boolean;
  filters: {
    last_checked_before_days: boolean;
    has_failed_files: boolean;
  };
  stale_filter_days: number;
  actions: WorkflowAction[];
  download_scope: DownloadScope;
  force_rescan: boolean;
  max_artworks: string;
  min_artwork_id: string;
  max_artwork_id: string;
  naming_rule: string;
  rules: RuleConfig;
};

type DraftWorkflow = {
  id: string;
  form: WorkflowForm;
  createdAt: string;
  updatedAt?: string;
};

const requiredModules: ModuleKey[] = ["target", "actions"];
const moduleOrder: ModuleKey[] = ["schedule", "target", "filters", "actions", "options", "naming", "rule"];
const targetOptions: WorkflowTarget[] = ["artists", "artworks", "all_artists", "artists_with_tag", "artists_not_checked"];
const draftsStorageKey = "pixivdownloader.workflowDrafts.v1";
const defaultNamingRule = "{artist}-{artist_id}/{original_filename}";
const namingTokens = [
  "{artist}",
  "{artist_id}",
  "{artwork_id}",
  "{title}",
  "{page}",
  "{original_filename}",
  "{ext}",
  "{type}",
  "{download_date}",
  "{ai}"
];

const initialForm: WorkflowForm = {
  name: "",
  modules: {
    schedule: false,
    target: true,
    filters: false,
    actions: true,
    options: false,
    naming: false,
    rule: false
  },
  interval_days: 30,
  enabled: true,
  run_after_startup: true,
  target_type: "artists",
  artist_id: "",
  artwork_id: "",
  artist_ids: [],
  artist_id_input: "",
  artwork_ids: [],
  artwork_id_input: "",
  artist_source: "artist_ids",
  tags: [],
  stale_target_days: 30,
  max_artists_per_run: 25,
  artist_selection: "oldest_checked_first",
  skip_unavailable_artists: true,
  filters: {
    last_checked_before_days: false,
    has_failed_files: false
  },
  stale_filter_days: 30,
  actions: ["download_artist"],
  download_scope: "incremental",
  force_rescan: false,
  max_artworks: "",
  min_artwork_id: "",
  max_artwork_id: "",
  naming_rule: defaultNamingRule,
  rules: {
    only_new_artworks: false,
    stop_if_artwork_count_above: false,
    artwork_count_limit: "",
    skip_if_last_run_failed: false,
    tag_variant_enabled: false,
    tag_variant_tag: "",
    tag_variant_behavior: "download",
    tag_variant_naming_rule: "{artist}-{artist_id}/{ai}/{original_filename}"
  }
};

const workflowStatusItems: Array<{ value: WorkflowStatusTab; label: string }> = [
  { value: "active", label: "Active" },
  { value: "failed", label: "Failed" },
  { value: "completed", label: "Complete" }
];

const moduleLabels: Record<ModuleKey, string> = {
  schedule: "Schedule",
  target: "Target",
  filters: "Filters",
  actions: "Actions",
  options: "Options",
  naming: "Naming",
  rule: "Rule"
};

const actionLabels: Record<WorkflowAction, string> = {
  download_artist: "Download",
  sync_artist: "Sync metadata",
  retry_failed_artist: "Retry failed files"
};

const tagVariantBehaviorLabels: Record<TagVariantBehavior, string> = {
  download: "Download normally",
  skip: "Skip download",
  retry_failed: "Retry failed files only"
};

const targetLabels: Record<WorkflowTarget, string> = {
  artists: "Artists",
  artworks: "Artworks",
  single_artist: "Single artist",
  single_artwork: "Single artwork",
  all_artists: "All artists",
  artists_with_tag: "Artists with tag",
  artists_not_checked: "Artists not checked"
};

const artistSelectionLabels: Record<ScheduledTaskArtistSelection, string> = {
  oldest_checked_first: "Oldest checked first",
  newest_checked_first: "Newest checked first",
  random: "Random"
};

export function WorkflowsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [drafts, setDrafts] = React.useState<DraftWorkflow[]>([]);
  const [selectedDraftId, setSelectedDraftId] = React.useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editingDraftId, setEditingDraftId] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<WorkflowForm>(initialForm);
  const [submitted, setSubmitted] = React.useState(false);
  const [statusTab, setStatusTab] = React.useState<WorkflowStatusTab>("active");
  const [submittedSearch, setSubmittedSearch] = React.useState("");
  const [archiveFilter, setArchiveFilter] = React.useState<ArchiveFilter>("normal");
  const [selectedRun, setSelectedRun] = React.useState<WorkflowBatchRun | null>(null);
  const [tagSearch, setTagSearch] = React.useState("");
  const [tagPickerOpen, setTagPickerOpen] = React.useState(false);

  React.useEffect(() => {
    const storedDrafts = loadStoredDrafts();
    if (storedDrafts.length) {
      setDrafts(storedDrafts);
      setSelectedDraftId(storedDrafts[0].id);
    }
  }, []);

  React.useEffect(() => {
    window.localStorage.setItem(draftsStorageKey, JSON.stringify(drafts));
  }, [drafts]);

  const jobs = useQuery({
    queryKey: ["jobs", "workflows", 100],
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
    refetchInterval: 15000
  });
  const selectedRunJobs = useQuery({
    queryKey: ["workflow-run-jobs", selectedRun?.id],
    queryFn: () => Promise.all(runJobIds(selectedRun).map((jobId) => getJob(jobId))),
    enabled: Boolean(selectedRun),
    refetchInterval: selectedRun?.status === "running" ? 4000 : false
  });
  const localTags = useQuery({ queryKey: ["local-tags"], queryFn: listLocalTags });
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings });

  const limitMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => {
      pushToast({ title: "Workflow limits synced", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
      invalidateRuntimeQueries(queryClient);
    },
    onError: (error) => pushToast({ title: "Workflow limits could not sync", description: error.message, tone: "error" })
  });

  const selectedDraft = drafts.find((draft) => draft.id === selectedDraftId) ?? drafts[0] ?? null;
  const errors = validateForm(form);
  const firstError = errors[0] ?? null;
  const canSubmit = errors.length === 0;

  const runDraftMutation = useMutation({
    mutationFn: (draft: DraftWorkflow) => submitDraft(draft.form),
    onSuccess: (response, draft) => {
      setDrafts((current) => current.filter((item) => item.id !== draft.id));
      setSelectedDraftId((current) => (current === draft.id ? null : current));
      pushToast({
        title: "Workflow submitted",
        description: response.jobIds.length ? `${response.jobIds.length} job(s)` : "Schedule created",
        tone: "success"
      });
      invalidateRuntimeQueries(queryClient);
    },
    onError: (error) => pushToast({ title: "Workflow could not run", description: error.message, tone: "error" })
  });

  const runAllMutation = useMutation({
    mutationFn: (request: { items: DraftWorkflow[]; concurrency: number }) =>
      createWorkflowRun({
        concurrency: request.concurrency,
        items: request.items.map((draft) => ({
          draft_id: draft.id,
          title: draftTitle(draft.form),
          config: workflowToConfig(draft.form),
          skip_if_last_run_failed:
            draft.form.modules.rule &&
            draft.form.rules.skip_if_last_run_failed &&
            lastRunItemStatus(draft.id, workflowRuns.data?.items ?? []) === "failed",
          schedule: draft.form.modules.schedule,
          name: draft.form.name.trim(),
          interval_days: draft.form.interval_days,
          enabled: draft.form.enabled,
          run_after_startup: draft.form.run_after_startup
        }))
      }),
    onSuccess: (batch) => {
      const ids = new Set(
        batch.items.filter((item) => item.status === "completed").map((item) => item.draft_id)
      );
      setDrafts((current) => current.filter((item) => !ids.has(item.id)));
      setSelectedDraftId(null);
      pushToast({
        title: "Draft queue submitted",
        description: `${batch.completed}/${batch.total} completed, ${batch.skipped} skipped`,
        tone: batch.failed ? "error" : "success"
      });
      invalidateRuntimeQueries(queryClient);
      void queryClient.invalidateQueries({ queryKey: ["workflow-runs"] });
    },
    onError: (error) => pushToast({ title: "Draft queue stopped", description: error.message, tone: "error" })
  });

  function openNewBuilder() {
    setEditingDraftId(null);
    setForm(initialForm);
    setSubmitted(false);
    setDialogOpen(true);
  }

  function openEditBuilder(draft: DraftWorkflow) {
    setEditingDraftId(draft.id);
    setForm(draft.form);
    setSubmitted(false);
    setDialogOpen(true);
  }

  function closeBuilder() {
    setDialogOpen(false);
    setEditingDraftId(null);
    setForm(initialForm);
    setSubmitted(false);
    setTagSearch("");
    setTagPickerOpen(false);
  }

  function saveDraft(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    if (!canSubmit) {
      return;
    }
    if (editingDraftId) {
      setDrafts((current) =>
        current.map((draft) =>
          draft.id === editingDraftId ? { ...draft, form, updatedAt: new Date().toISOString() } : draft
        )
      );
      setSelectedDraftId(editingDraftId);
      pushToast({ title: "Draft updated", tone: "success" });
    } else {
      const draft = { id: crypto.randomUUID(), form, createdAt: new Date().toISOString() };
      setDrafts((current) => [draft, ...current]);
      setSelectedDraftId(draft.id);
      pushToast({ title: "Draft added", tone: "success" });
    }
    closeBuilder();
  }

  const rawRuns = workflowRuns.data?.items ?? [];
  const rawSchedules = schedules.data?.items ?? [];
  const rawWaitingJobs = workflowWaitingJobs(jobs.data?.items ?? []);
  const allRuns = filterWorkflowRuns(rawRuns, submittedSearch);
  const allSchedules = filterSchedules(rawSchedules, submittedSearch);
  const waitingJobs = archiveFilter === "archived" ? [] : filterWaitingJobs(rawWaitingJobs, submittedSearch);
  const runGroups = archiveFilter === "archived" ? emptyRunGroups() : workflowRunGroups(allRuns);
  const scheduleGroups = workflowScheduleGroups(allSchedules);
  const visibleScheduleGroups = {
    active: archiveFilter === "archived" ? [] : scheduleGroups.active,
    blocked: archiveFilter === "archived" ? [] : scheduleGroups.blocked,
    inactive: archiveFilter === "archived" ? [] : scheduleGroups.inactive,
    archived: archiveFilter === "normal" ? [] : scheduleGroups.archived
  };
  const activeCount = runGroups.active.length + waitingJobs.length + visibleScheduleGroups.active.length;
  const failedCount = runGroups.failed.length + visibleScheduleGroups.blocked.length;
  const failedRunReasonGroups = groupRunsByFailureReason(runGroups.failed);
  const failedScheduleReasonGroups = groupSchedulesByFailureReason(visibleScheduleGroups.blocked);
  const completedCount =
    runGroups.completed.length + visibleScheduleGroups.inactive.length + visibleScheduleGroups.archived.length;
  const submittedCount =
    statusTab === "active" ? activeCount : statusTab === "failed" ? failedCount : completedCount;

  return (
    <>
      <PageHeader
        title="Workflows"
        description="Stage workflow drafts, then submit them into runs or schedules."
        actions={
          <>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                void jobs.refetch();
                void schedules.refetch();
                void workflowRuns.refetch();
              }}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Refresh
            </Button>
            <Button type="button" onClick={openNewBuilder}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add Workflow
            </Button>
          </>
        }
      />

      <div className="grid gap-4 p-4 sm:p-6 xl:grid-cols-[390px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <section className="surface p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">Draft Queue</h2>
                <p className="mt-1 text-sm text-muted-foreground">{drafts.length} staged workflow(s)</p>
              </div>
              <Button type="button" size="sm" onClick={openNewBuilder}>
                <Plus className="h-4 w-4" aria-hidden="true" />
                Add
              </Button>
            </div>

            <div className="mt-4 space-y-2">
              {drafts.length === 0 ? (
                <p className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">
                  Add workflows here before submitting them.
                </p>
              ) : (
                drafts.map((draft) => (
                  <DraftQueueItem
                    key={draft.id}
                    draft={draft}
                    selected={selectedDraft?.id === draft.id}
                    running={runDraftMutation.isPending}
                    onSelect={() => setSelectedDraftId(draft.id)}
                    onEdit={() => openEditBuilder(draft)}
                    onDuplicate={() => {
                      const copyDraft = {
                        id: crypto.randomUUID(),
                        form: { ...draft.form, name: draft.form.name ? `${draft.form.name} copy` : "" },
                        createdAt: new Date().toISOString()
                      };
                      setDrafts((current) => [copyDraft, ...current]);
                      setSelectedDraftId(copyDraft.id);
                    }}
                    onRun={() => runDraftMutation.mutate(draft)}
                    onDelete={() => {
                      setDrafts((current) => current.filter((item) => item.id !== draft.id));
                      setSelectedDraftId((current) => (current === draft.id ? null : current));
                    }}
                  />
                ))
              )}
            </div>

            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              <Button
                type="button"
                variant="outline"
                disabled={drafts.length === 0 || runAllMutation.isPending}
                onClick={() =>
                  runAllMutation.mutate({
                    items: drafts,
                    concurrency: clampConcurrency(settings.data?.max_active_one_time_tasks ?? 1)
                  })
                }
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                Run All
              </Button>
              <Button
                type="button"
                variant="ghost"
                disabled={drafts.length === 0}
                onClick={() => {
                  setDrafts([]);
                  setSelectedDraftId(null);
                }}
              >
                Clear
              </Button>
            </div>
          </section>

          {selectedDraft ? (
            <DraftDetail draft={selectedDraft} onEdit={() => openEditBuilder(selectedDraft)} />
          ) : (
            <DataState title="No draft selected" description="Draft details appear here." />
          )}
        </aside>

        <section className="space-y-4">
          <div className="surface p-4">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <h2 className="text-sm font-semibold">Submitted</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Runs are execution records. Schedules create future runs automatically.
                </p>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center xl:justify-end">
                {statusTab === "active" ? (
                  <WorkflowLimitPanel
                    jobs={jobs.data?.items ?? []}
                    settings={settings.data}
                    disabled={settings.isLoading || limitMutation.isPending}
                    onSync={(key, value) => limitMutation.mutate({ [key]: value })}
                  />
                ) : null}
                <Tabs value={statusTab} onValueChange={setStatusTab} items={workflowStatusItems} />
                <p className="whitespace-nowrap text-sm text-muted-foreground">{submittedCount} item(s)</p>
              </div>
            </div>
          </div>
          <SubmittedToolbar
            search={submittedSearch}
            archiveFilter={archiveFilter}
            onSearchChange={setSubmittedSearch}
            onArchiveFilterChange={setArchiveFilter}
          />
          {jobs.isError ? (
            <DataState title="Could not load jobs" description={jobs.error.message} variant="error" />
          ) : workflowRuns.isError ? (
            <DataState title="Could not load workflow runs" description={workflowRuns.error.message} variant="error" />
          ) : schedules.isError ? (
            <DataState title="Could not load schedules" description={schedules.error.message} variant="error" />
          ) : jobs.isLoading || workflowRuns.isLoading || schedules.isLoading ? (
            <DataState title="Loading submitted workflows" variant="loading" />
          ) : submittedCount === 0 ? (
            <DataState title="No submitted workflows here" description="Submit a draft or choose another state." />
          ) : statusTab === "active" ? (
            <div className="space-y-4">
              <WorkflowGroupSection title="Running Runs" count={runGroups.active.length}>
                {runGroups.active.map((run) => (
                  <RunWorkflowCard key={run.id} run={run} onInspect={() => setSelectedRun(run)} />
                ))}
              </WorkflowGroupSection>
              <WorkflowGroupSection title="Waiting Queue" count={waitingJobs.length}>
                {waitingJobs.map((job) => (
                  <WaitingJobCard key={job.id} job={job} />
                ))}
              </WorkflowGroupSection>
              <WorkflowGroupSection title="Active Schedules" count={visibleScheduleGroups.active.length}>
                {visibleScheduleGroups.active.map((task) => (
                  <ScheduleWorkflowCard key={`schedule-${task.id}`} task={task} lastRun={latestScheduleRun(task, rawRuns)} />
                ))}
              </WorkflowGroupSection>
            </div>
          ) : statusTab === "failed" ? (
            <div className="space-y-4">
              {failedRunReasonGroups.map((group) => (
                <WorkflowGroupSection key={`runs-${group.reason}`} title={`Failed Runs · ${group.reason}`} count={group.items.length}>
                  {group.items.map((run) => (
                    <RunWorkflowCard key={run.id} run={run} onInspect={() => setSelectedRun(run)} />
                  ))}
                </WorkflowGroupSection>
              ))}
              {failedScheduleReasonGroups.map((group) => (
                <WorkflowGroupSection key={`schedules-${group.reason}`} title={`Blocked Schedules · ${group.reason}`} count={group.items.length}>
                  {group.items.map((task) => (
                    <ScheduleWorkflowCard key={`schedule-${task.id}`} task={task} lastRun={latestScheduleRun(task, rawRuns)} />
                  ))}
                </WorkflowGroupSection>
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              {archiveFilter !== "archived" ? (
                <>
                  <WorkflowGroupSection title="Completed Runs" count={runGroups.completed.length}>
                    {runGroups.completed.map((run) => (
                      <RunWorkflowCard key={run.id} run={run} onInspect={() => setSelectedRun(run)} />
                    ))}
                  </WorkflowGroupSection>
                  <WorkflowGroupSection title="Inactive Schedules" count={visibleScheduleGroups.inactive.length}>
                    {visibleScheduleGroups.inactive.map((task) => (
                      <ScheduleWorkflowCard key={`schedule-${task.id}`} task={task} lastRun={latestScheduleRun(task, rawRuns)} />
                    ))}
                  </WorkflowGroupSection>
                </>
              ) : null}
              {archiveFilter !== "normal" ? (
                <WorkflowGroupSection title="Archived Schedules" count={visibleScheduleGroups.archived.length}>
                  {visibleScheduleGroups.archived.map((task) => (
                    <ScheduleWorkflowCard key={`schedule-${task.id}`} task={task} lastRun={latestScheduleRun(task, rawRuns)} />
                  ))}
                </WorkflowGroupSection>
              ) : null}
            </div>
          )}
        </section>
      </div>

      <Dialog
        open={dialogOpen}
        title={editingDraftId ? "Edit workflow draft" : "Add workflow draft"}
        description="Select modules to insert their cards into the workflow."
        className="flex h-[92vh] max-w-5xl flex-col overflow-hidden"
        bodyClassName="min-h-0 flex-1 overflow-hidden"
        onOpenChange={(open) => (open ? setDialogOpen(true) : closeBuilder())}
        footer={
          <>
            <Button type="button" variant="outline" onClick={closeBuilder}>Cancel</Button>
            <Button type="submit" form="workflow-builder" disabled={!canSubmit}>
              <ListPlus className="h-4 w-4" aria-hidden="true" />
              {editingDraftId ? "Update Draft" : "Add To Queue"}
            </Button>
          </>
        }
      >
        <form id="workflow-builder" className="flex h-full min-h-0 flex-col gap-4" onSubmit={saveDraft}>
          <div className="shrink-0 space-y-4">
            <ModuleToggleBar form={form} setForm={setForm} />
            {submitted && firstError ? (
              <p className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                {firstError}
              </p>
            ) : null}
          </div>
          <div className="grid min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-[minmax(0,1fr)_280px]">
            <div className="min-h-0 overflow-y-auto overscroll-contain pr-1">
              <div className="space-y-4">
              {moduleOrder.filter((module) => form.modules[module]).map((module) => (
                <ModuleCard key={module} module={module}>
                  {module === "schedule" ? <ScheduleCard form={form} setForm={setForm} /> : null}
                  {module === "target" ? (
                    <TargetCard
                      form={form}
                      setForm={setForm}
                      localTags={localTags.data?.items ?? []}
                      tagSearch={tagSearch}
                      tagPickerOpen={tagPickerOpen}
                      setTagSearch={setTagSearch}
                      setTagPickerOpen={setTagPickerOpen}
                    />
                  ) : null}
                  {module === "filters" ? <FiltersCard form={form} setForm={setForm} /> : null}
                  {module === "actions" ? <ActionsCard form={form} setForm={setForm} /> : null}
                  {module === "options" ? <OptionsCard form={form} setForm={setForm} /> : null}
                  {module === "naming" ? <NamingCard form={form} setForm={setForm} /> : null}
                  {module === "rule" ? <RuleCard form={form} setForm={setForm} /> : null}
                </ModuleCard>
              ))}
              </div>
            </div>
            <aside className="min-h-0 space-y-3 overflow-y-auto overscroll-contain pr-1">
              <div className="rounded-md border bg-muted/20 p-3 text-sm">
                <p className="font-medium">Preview</p>
                <p className="mt-2 text-muted-foreground">{canSubmit ? previewText(form) : firstError}</p>
              </div>
              {form.modules.schedule && form.download_scope === "full" ? (
                <p className="status-warning rounded-md border p-3 text-sm">
                  Full download schedules re-check already tracked works every run.
                </p>
              ) : null}
            </aside>
          </div>
        </form>
      </Dialog>
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

function ModuleToggleBar({ form, setForm }: { form: WorkflowForm; setForm: (form: WorkflowForm) => void }): JSX.Element {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2">
      {moduleOrder.map((module) => {
        const required = requiredModules.includes(module);
        return (
          <label
            key={module}
            className={cn(
              "flex min-h-8 items-center gap-2 text-sm",
              form.modules[module] && "text-primary",
              required && "cursor-not-allowed opacity-80"
            )}
          >
            <input
              type="checkbox"
              checked={form.modules[module]}
              disabled={required}
              onChange={(event) =>
                setForm({ ...form, modules: { ...form.modules, [module]: event.target.checked } })
              }
            />
            {moduleLabels[module]}
          </label>
        );
      })}
    </div>
  );
}

function ModuleCard({ module, children }: { module: ModuleKey; children: React.ReactNode }): JSX.Element {
  return (
    <section className="rounded-md border bg-card p-4 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <ModuleIcon module={module} />
        <h3 className="text-sm font-semibold">{moduleLabels[module]}</h3>
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function ScheduleCard({ form, setForm }: { form: WorkflowForm; setForm: (form: WorkflowForm) => void }): JSX.Element {
  return (
    <>
      <Field label="Name">
        <Input
          value={form.name}
          placeholder="Monthly favorite updates"
          onChange={(event) => setForm({ ...form, name: event.target.value })}
        />
      </Field>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Interval days">
          <Input
            type="number"
            min={1}
            value={form.interval_days}
            onChange={(event) => setForm({ ...form, interval_days: Number(event.target.value) })}
          />
        </Field>
        <label className="flex min-h-10 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
          />
          Enabled
        </label>
        <label className="flex min-h-10 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.run_after_startup}
            onChange={(event) => setForm({ ...form, run_after_startup: event.target.checked })}
          />
          Run on restart
        </label>
      </div>
    </>
  );
}

function TargetCard({
  form,
  setForm,
  localTags,
  tagSearch,
  tagPickerOpen,
  setTagSearch,
  setTagPickerOpen
}: {
  form: WorkflowForm;
  setForm: (form: WorkflowForm) => void;
  localTags: LocalTag[];
  tagSearch: string;
  tagPickerOpen: boolean;
  setTagSearch: (value: string) => void;
  setTagPickerOpen: (value: boolean) => void;
}): JSX.Element {
  const multiArtistTarget = isMultiArtistTarget(form.target_type);
  return (
    <>
      <div>
        <p className="mb-2 text-sm font-medium">Target type</p>
        <div className="flex flex-wrap gap-2">
          {targetOptions.map((target) => (
            <button
              key={target}
              type="button"
              className={cn(
                "min-h-9 rounded-md border px-3 text-sm",
                form.target_type === target
                  ? "border-primary bg-primary text-primary-foreground"
                  : "bg-background hover:bg-muted"
              )}
              onClick={() =>
                setForm({
                  ...form,
                  target_type: target,
                  actions: target === "single_artwork" || target === "artworks" ? ["download_artist"] : form.actions
                })
              }
            >
              {targetLabels[target]}
            </button>
          ))}
        </div>
      </div>
      {form.target_type === "artists" ? (
        <ArtistsTargetFields form={form} setForm={setForm} />
      ) : null}
      {form.target_type === "artworks" ? (
        <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          Artwork-only downloads are reserved for the next step. Use Artists with Artwork ID input to download the owning artist for now.
        </div>
      ) : null}
      {form.target_type === "single_artist" ? (
        <Field label="Pixiv artist ID">
          <Input
            inputMode="numeric"
            value={form.artist_id}
            placeholder="123456"
            onChange={(event) => setForm({ ...form, artist_id: event.target.value })}
          />
        </Field>
      ) : null}
      {form.target_type === "single_artwork" ? (
        <Field label="Pixiv artwork ID">
          <Input
            inputMode="numeric"
            value={form.artwork_id}
            placeholder="987654321"
            onChange={(event) => setForm({ ...form, artwork_id: event.target.value })}
          />
        </Field>
      ) : null}
      {form.target_type === "artists_with_tag" ? (
        <Field label="Local tags">
          <TagPicker
            tags={localTags}
            selectedTags={form.tags}
            search={tagSearch}
            open={tagPickerOpen}
            onSearchChange={(value) => {
              setTagSearch(value);
              setTagPickerOpen(true);
            }}
            onOpenChange={setTagPickerOpen}
            onSelect={(tag) => {
              setForm({ ...form, tags: toggleItem(form.tags, tag, true) });
              setTagSearch("");
              setTagPickerOpen(true);
            }}
            onRemove={(tag) => setForm({ ...form, tags: toggleItem(form.tags, tag, false) })}
          />
        </Field>
      ) : null}
      {form.target_type === "artists_not_checked" ? (
        <Field label="Not checked for days">
          <Input
            type="number"
            min={1}
            value={form.stale_target_days}
            onChange={(event) => setForm({ ...form, stale_target_days: Number(event.target.value) })}
          />
        </Field>
      ) : null}
      {multiArtistTarget ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Max targets per run">
            <Input
              type="number"
              min={1}
              value={form.max_artists_per_run}
              onChange={(event) => setForm({ ...form, max_artists_per_run: Number(event.target.value) })}
            />
          </Field>
          <Field label="Order">
            <Select
              value={form.artist_selection}
              onChange={(event) =>
                setForm({
                  ...form,
                  artist_selection: event.target.value as ScheduledTaskArtistSelection
                })
              }
            >
              {Object.entries(artistSelectionLabels).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </Select>
          </Field>
          <label className="flex min-h-10 items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.skip_unavailable_artists}
              onChange={(event) => setForm({ ...form, skip_unavailable_artists: event.target.checked })}
            />
            Skip unavailable
          </label>
        </div>
      ) : null}
    </>
  );
}

function ArtistsTargetFields({
  form,
  setForm
}: {
  form: WorkflowForm;
  setForm: (form: WorkflowForm) => void;
}): JSX.Element {
  const ids = form.artist_source === "artist_ids" ? form.artist_ids : form.artwork_ids;
  const inputValue = form.artist_source === "artist_ids" ? form.artist_id_input : form.artwork_id_input;
  const inputKey = form.artist_source === "artist_ids" ? "artist_id_input" : "artwork_id_input";
  const idsKey = form.artist_source === "artist_ids" ? "artist_ids" : "artwork_ids";
  const placeholder = form.artist_source === "artist_ids" ? "123456" : "987654321";

  const addIds = () => {
    const nextIds = appendNumericIds(ids, inputValue);
    setForm({ ...form, [idsKey]: nextIds, [inputKey]: "" });
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <Select
          className="w-40 shrink-0"
          value={form.artist_source}
          onChange={(event) => {
            const artist_source = event.target.value as ArtistTargetSource;
            setForm({
              ...form,
              artist_source
            });
          }}
        >
          <option value="artist_ids">Artist IDs</option>
          <option value="artwork_ids">Artwork IDs</option>
        </Select>
        <Input
          inputMode="numeric"
          value={inputValue}
          placeholder={placeholder}
          aria-label={form.artist_source === "artist_ids" ? "Artist ID" : "Artwork ID"}
          onChange={(event) => setForm({ ...form, [inputKey]: event.target.value })}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addIds();
            }
          }}
        />
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="shrink-0"
          onClick={addIds}
          title="Add ID"
          aria-label="Add ID"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      <div className="space-y-3">
        <IdQueue
          title="Artist IDs"
          emptyText="No artist IDs added"
          ids={form.artist_ids}
          onRemove={(id) => setForm({ ...form, artist_ids: form.artist_ids.filter((item) => item !== id) })}
        />
        <IdQueue
          title="Artwork IDs"
          emptyText="No artwork IDs added"
          ids={form.artwork_ids}
          onRemove={(id) => setForm({ ...form, artwork_ids: form.artwork_ids.filter((item) => item !== id) })}
        />
      </div>
    </div>
  );
}

function IdQueue({
  title,
  emptyText,
  ids,
  onRemove
}: {
  title: string;
  emptyText: string;
  ids: string[];
  onRemove: (id: string) => void;
}): JSX.Element {
  return (
    <div>
      <p className="mb-2 text-xs font-medium text-muted-foreground">{title} · {ids.length}</p>
      {ids.length ? (
        <div className="flex flex-wrap gap-2">
          {ids.map((id) => (
            <Badge key={id} tone="muted">
              <span>{id}</span>
              <button
                type="button"
                className="ml-1 text-muted-foreground hover:text-foreground"
                onClick={() => onRemove(id)}
                aria-label={`Remove ${id}`}
              >
                x
              </button>
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      )}
    </div>
  );
}

function FiltersCard({ form, setForm }: { form: WorkflowForm; setForm: (form: WorkflowForm) => void }): JSX.Element {
  return (
    <>
      <label className="flex min-h-10 items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.filters.last_checked_before_days}
          onChange={(event) =>
            setForm({
              ...form,
              filters: { ...form.filters, last_checked_before_days: event.target.checked }
            })
          }
        />
        Last checked before
      </label>
      {form.filters.last_checked_before_days ? (
        <Field label="Older than days">
          <Input
            type="number"
            min={1}
            value={form.stale_filter_days}
            onChange={(event) => setForm({ ...form, stale_filter_days: Number(event.target.value) })}
          />
        </Field>
      ) : null}
      <label className="flex min-h-10 items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.filters.has_failed_files}
          onChange={(event) =>
            setForm({ ...form, filters: { ...form.filters, has_failed_files: event.target.checked } })
          }
        />
        Has failed files
      </label>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Max artworks">
          <Input
            inputMode="numeric"
            value={form.max_artworks}
            placeholder="No limit"
            onChange={(event) => setForm({ ...form, max_artworks: event.target.value })}
          />
        </Field>
        <Field label="Artwork ID from">
          <Input
            inputMode="numeric"
            value={form.min_artwork_id}
            placeholder="Min"
            onChange={(event) => setForm({ ...form, min_artwork_id: event.target.value })}
          />
        </Field>
        <Field label="Artwork ID to">
          <Input
            inputMode="numeric"
            value={form.max_artwork_id}
            placeholder="Max"
            onChange={(event) => setForm({ ...form, max_artwork_id: event.target.value })}
          />
        </Field>
      </div>
    </>
  );
}

function ActionsCard({ form, setForm }: { form: WorkflowForm; setForm: (form: WorkflowForm) => void }): JSX.Element {
  const artworkTarget = form.target_type === "single_artwork" || form.target_type === "artworks";
  return (
    <>
      {(Object.keys(actionLabels) as WorkflowAction[]).map((action) => {
        const disabled = artworkTarget && action !== "download_artist";
        return (
          <label
            key={action}
            className={cn(
              "flex min-h-10 items-center gap-2 text-sm",
              disabled && "opacity-50"
            )}
          >
            <input
              type="checkbox"
              checked={form.actions.includes(action)}
              disabled={disabled}
              onChange={(event) => {
                const actions = toggleItem(form.actions, action, event.target.checked);
                setForm({
                  ...form,
                  actions,
                  download_scope: actions.includes("retry_failed_artist") ? "incremental" : form.download_scope
                });
              }}
            />
            {actionLabels[action]}
          </label>
        );
      })}
    </>
  );
}

function OptionsCard({ form, setForm }: { form: WorkflowForm; setForm: (form: WorkflowForm) => void }): JSX.Element {
  const retryOnly = form.actions.includes("retry_failed_artist");
  return (
    <>
      <Field label="Download scope">
        <Select
          value={form.download_scope}
          disabled={retryOnly}
          onChange={(event) => {
            const download_scope = event.target.value as DownloadScope;
            setForm({ ...form, download_scope });
          }}
        >
          <option value="incremental">New works only</option>
          <option value="full">All discovered works</option>
        </Select>
      </Field>
      {retryOnly ? (
        <p className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">
          Retry failed files is controlled by the Actions module.
        </p>
      ) : null}
      <label className="flex min-h-10 items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.force_rescan}
          onChange={(event) => setForm({ ...form, force_rescan: event.target.checked })}
        />
        Force rescan
      </label>
      <p className="text-sm text-muted-foreground">Existing file handling follows the Settings download behavior.</p>
    </>
  );
}

function NamingCard({ form, setForm }: { form: WorkflowForm; setForm: (form: WorkflowForm) => void }): JSX.Element {
  const rule = form.naming_rule || defaultNamingRule;
  return (
    <>
      <Field label="Path and filename rule">
        <Input
          value={rule}
          placeholder={defaultNamingRule}
          onChange={(event) => setForm({ ...form, naming_rule: event.target.value })}
        />
      </Field>
      <div className="rounded-md border bg-muted/20 p-3 text-sm">
        <p className="font-medium">Preview</p>
        <p className="mt-2 break-all text-muted-foreground">
          {previewNamingRule(rule)}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {namingTokens.map((token) => (
          <button
            key={token}
            type="button"
            className="rounded-md border bg-background px-2 py-1 text-xs hover:bg-muted"
            onClick={() => setForm({ ...form, naming_rule: `${rule}${token}` })}
          >
            {token}
          </button>
        ))}
      </div>
    </>
  );
}

function RuleCard({ form, setForm }: { form: WorkflowForm; setForm: (form: WorkflowForm) => void }): JSX.Element {
  return (
    <>
      <label className="flex min-h-10 items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.rules.only_new_artworks}
          onChange={(event) =>
            setForm({ ...form, rules: { ...form.rules, only_new_artworks: event.target.checked } })
          }
        />
        Only run if found new artworks
      </label>
      <label className="flex min-h-10 items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.rules.stop_if_artwork_count_above}
          onChange={(event) =>
            setForm({ ...form, rules: { ...form.rules, stop_if_artwork_count_above: event.target.checked } })
          }
        />
        Stop if artwork count is above
      </label>
      {form.rules.stop_if_artwork_count_above ? (
        <Field label="Artwork count limit">
          <Input
            inputMode="numeric"
            value={form.rules.artwork_count_limit}
            placeholder="500"
            onChange={(event) =>
              setForm({ ...form, rules: { ...form.rules, artwork_count_limit: event.target.value } })
            }
          />
        </Field>
      ) : null}
      <label className="flex min-h-10 items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.rules.skip_if_last_run_failed}
          onChange={(event) =>
            setForm({ ...form, rules: { ...form.rules, skip_if_last_run_failed: event.target.checked } })
          }
        />
        Skip if last run failed
      </label>
      <label className="flex min-h-10 items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.rules.tag_variant_enabled}
          onChange={(event) =>
            setForm({ ...form, rules: { ...form.rules, tag_variant_enabled: event.target.checked } })
          }
        />
        Run tag behavior variant when artwork tag matches
      </label>
      {form.rules.tag_variant_enabled ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Matching tag">
            <Input
              value={form.rules.tag_variant_tag}
              placeholder="AI生成"
              onChange={(event) =>
                setForm({ ...form, rules: { ...form.rules, tag_variant_tag: event.target.value } })
              }
            />
          </Field>
          <Field label="Matching tag behavior">
            <Select
              value={form.rules.tag_variant_behavior}
              onChange={(event) =>
                setForm({
                  ...form,
                  rules: { ...form.rules, tag_variant_behavior: event.target.value as TagVariantBehavior }
                })
              }
            >
              {Object.entries(tagVariantBehaviorLabels).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </Select>
          </Field>
          <Field label="Variant naming">
            <Input
              value={form.rules.tag_variant_naming_rule}
              placeholder="{artist}-{artist_id}/{ai}/{original_filename}"
              onChange={(event) =>
                setForm({ ...form, rules: { ...form.rules, tag_variant_naming_rule: event.target.value } })
              }
            />
          </Field>
        </div>
      ) : null}
    </>
  );
}

function RunWorkflowCard({ run, onInspect }: { run: WorkflowBatchRun; onInspect: () => void }): JSX.Element {
  return (
    <article className="surface p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-sm font-semibold">{runTitle(run)}</h2>
            <WorkflowRunStatusPill status={run.status} />
            <Badge tone="muted">run</Badge>
            {run.source === "schedule" || run.source === "manual_schedule" ? (
              <Badge tone="default">{run.source === "manual_schedule" ? "manual schedule" : "schedule"}</Badge>
            ) : null}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {run.completed}/{run.total} completed, {run.failed} failed, {run.skipped} skipped
          </p>
        </div>
        <div className="text-left text-sm text-muted-foreground sm:text-right">
          <div>{formatDate(run.created_at)}</div>
          <div className="mt-1">Concurrency {run.concurrency}</div>
          <Button type="button" size="sm" variant="outline" className="mt-2" onClick={onInspect}>
            Inspect
          </Button>
        </div>
      </div>
      <div className="mt-3 space-y-2">
        {run.items.map((item) => (
          <div key={item.id ?? item.draft_id} className="rounded-md border bg-muted/20 p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{item.title}</span>
              <Badge tone={workflowItemTone(item.status)}>
                {item.status}
              </Badge>
            </div>
            {item.job_ids.length ? (
              <p className="mt-1 break-all text-xs text-muted-foreground">
                {item.job_ids.length} job(s): {item.job_ids.join(", ")}
              </p>
            ) : item.error_message ? (
              <p className="mt-1 break-words text-xs text-destructive">{item.error_message}</p>
            ) : (
              <p className="mt-1 text-xs text-muted-foreground">No job was created.</p>
            )}
          </div>
        ))}
      </div>
    </article>
  );
}

function SubmittedToolbar({
  search,
  archiveFilter,
  onSearchChange,
  onArchiveFilterChange
}: {
  search: string;
  archiveFilter: ArchiveFilter;
  onSearchChange: (value: string) => void;
  onArchiveFilterChange: (value: ArchiveFilter) => void;
}): JSX.Element {
  return (
    <form
      className="surface flex flex-col gap-3 p-3 sm:flex-row"
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      <div className="relative flex-1">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          className="pl-9"
          value={search}
          placeholder="Search submitted workflows"
          aria-label="Search submitted workflows"
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </div>
      <Select
        value={archiveFilter}
        aria-label="Archived filter"
        onChange={(event) => onArchiveFilterChange(event.target.value as ArchiveFilter)}
      >
        <option value="normal">Archived hidden</option>
        <option value="include">Include archived</option>
        <option value="archived">Archived only</option>
      </Select>
    </form>
  );
}

function WorkflowGroupSection({
  title,
  count,
  children
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}): JSX.Element {
  if (count === 0) {
    return (
      <section className="rounded-md border bg-muted/20 p-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{title}</h3>
          <Badge tone="muted">0</Badge>
        </div>
      </section>
    );
  }
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-2 px-1">
        <h3 className="text-sm font-semibold">{title}</h3>
        <Badge tone="muted">{count}</Badge>
      </div>
      <div className="grid gap-3">{children}</div>
    </section>
  );
}

function WaitingJobCard({ job }: { job: Job }): JSX.Element {
  return (
    <article className="surface p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-sm font-semibold">{jobLabel(job)}</h2>
            <Badge tone="muted">waiting</Badge>
            {job.workflow_source ? <Badge tone="default">{sourceLabel(job.workflow_source)}</Badge> : null}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{jobTarget(job)}</p>
        </div>
        <div className="text-left text-sm text-muted-foreground sm:text-right">
          <div>{formatDate(job.created_at)}</div>
          <div className="mt-1">{job.completed_files}/{job.total_files || 0} files</div>
        </div>
      </div>
    </article>
  );
}

function RunDetailDialog({
  run,
  jobs,
  loading,
  error,
  onOpenChange
}: {
  run: WorkflowBatchRun | null;
  jobs: JobDetail[];
  loading: boolean;
  error?: string;
  onOpenChange: (open: boolean) => void;
}): JSX.Element {
  return (
    <Dialog
      open={Boolean(run)}
      title={run ? runTitle(run) : "Run detail"}
      description={run ? `${sourceLabel(run.source)} · ${run.status} · ${formatDate(run.created_at)}` : undefined}
      className="flex h-[88vh] max-w-5xl flex-col overflow-hidden"
      bodyClassName="min-h-0 flex-1 overflow-y-auto pr-1"
      onOpenChange={onOpenChange}
    >
      {!run ? null : (
        <div className="space-y-4">
          <dl className="grid gap-3 text-sm sm:grid-cols-4">
            <Detail label="Source" value={sourceLabel(run.source)} />
            <Detail label="Schedule" value={run.schedule_id ? String(run.schedule_id) : "-"} />
            <Detail label="Created" value={formatDate(run.created_at)} />
            <Detail label="Finished" value={formatDate(run.finished_at)} />
          </dl>
          <section className="rounded-md border bg-muted/20 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <WorkflowRunStatusPill status={run.status} />
              <Badge tone="muted">{run.completed}/{run.total} completed</Badge>
              <Badge tone={run.failed ? "danger" : "muted"}>{run.failed} failed</Badge>
              <Badge tone={run.skipped ? "warning" : "muted"}>{run.skipped} skipped</Badge>
            </div>
          </section>
          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Items</h3>
            {run.items.map((item) => (
              <div key={item.id ?? item.draft_id} className="rounded-md border bg-card p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{item.title}</span>
                  <Badge tone={workflowItemTone(item.status)}>{item.status}</Badge>
                </div>
                <dl className="mt-3 grid gap-3 sm:grid-cols-3">
                  <Detail label="Draft" value={item.draft_id} />
                  <Detail label="Jobs" value={item.job_ids.length ? item.job_ids.join(", ") : "-"} />
                  <Detail label="Finished" value={formatDate(item.finished_at)} />
                </dl>
                {item.error_message ? (
                  <p className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                    {item.error_message}
                  </p>
                ) : null}
              </div>
            ))}
          </section>
          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Jobs</h3>
            {loading ? (
              <DataState title="Loading jobs" variant="loading" />
            ) : error ? (
              <DataState title="Could not load jobs" description={error} variant="error" />
            ) : jobs.length === 0 ? (
              <p className="rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">No jobs were created.</p>
            ) : (
              jobs.map((job) => <RunJobDetail key={job.id} job={job} />)
            )}
          </section>
        </div>
      )}
    </Dialog>
  );
}

function RunJobDetail({ job }: { job: JobDetail }): JSX.Element {
  const latestEvent = job.events.at(-1);
  return (
    <article className="rounded-md border bg-card p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="break-words text-sm font-semibold">{jobLabel(job)}</h4>
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
      ) : null}
      <div className="mt-3">
        {latestEvent ? (
          <div className="rounded-md border bg-muted/20 p-2 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Badge tone={latestEvent.level === "error" ? "danger" : latestEvent.level === "warning" ? "warning" : "muted"}>
                {latestEvent.level}
              </Badge>
              <span className="text-muted-foreground">{formatDate(latestEvent.created_at)}</span>
            </div>
            <p className="mt-1 break-words">{latestEvent.message}</p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No events recorded.</p>
        )}
      </div>
    </article>
  );
}

function DraftQueueItem({
  draft,
  selected,
  running,
  onSelect,
  onEdit,
  onDuplicate,
  onRun,
  onDelete
}: {
  draft: DraftWorkflow;
  selected: boolean;
  running: boolean;
  onSelect: () => void;
  onEdit: () => void;
  onDuplicate: () => void;
  onRun: () => void;
  onDelete: () => void;
}): JSX.Element {
  return (
    <article className={cn("rounded-md border bg-card p-3", selected && "border-primary/50 bg-primary/5")}>
      <button type="button" className="block w-full text-left" onClick={onSelect}>
        <div className="flex items-center justify-between gap-2">
          <h3 className="truncate text-sm font-semibold">{draftTitle(draft.form)}</h3>
          <Badge tone={draft.form.modules.schedule ? "default" : "muted"}>
            {draft.form.modules.schedule ? "schedule" : "one-off"}
          </Badge>
        </div>
        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{previewText(draft.form)}</p>
      </button>
      <div className="mt-3 flex flex-wrap gap-2">
        <IconButton title="Run" onClick={onRun} disabled={running}>
          <Play className="h-4 w-4" aria-hidden="true" />
        </IconButton>
        <IconButton title="Edit" onClick={onEdit}>
          <Pencil className="h-4 w-4" aria-hidden="true" />
        </IconButton>
        <IconButton title="Duplicate" onClick={onDuplicate}>
          <Copy className="h-4 w-4" aria-hidden="true" />
        </IconButton>
        <IconButton title="Delete" onClick={onDelete}>
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </IconButton>
      </div>
    </article>
  );
}

function DraftDetail({ draft, onEdit }: { draft: DraftWorkflow; onEdit: () => void }): JSX.Element {
  const activeModules = moduleOrder.filter((module) => draft.form.modules[module]);
  return (
    <section className="surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">{draftTitle(draft.form)}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{previewText(draft.form)}</p>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={onEdit}>
          <Pencil className="h-4 w-4" aria-hidden="true" />
          Edit
        </Button>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {activeModules.map((module) => (
          <Badge key={module} tone={module === "target" || module === "actions" ? "default" : "muted"}>
            {moduleLabels[module]}
          </Badge>
        ))}
      </div>
      <dl className="mt-4 grid gap-3 text-sm">
        <Detail label="Target" value={targetDetail(draft.form)} />
        <Detail label="Actions" value={draft.form.actions.map((action) => actionLabels[action]).join(", ")} />
        <Detail label="Created" value={formatDate(draft.createdAt)} />
      </dl>
    </section>
  );
}

function ScheduleWorkflowCard({
  task,
  lastRun
}: {
  task: ScheduledTask;
  lastRun: WorkflowBatchRun | null;
}): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const invalidate = () => invalidateRuntimeQueries(queryClient);
  const runMutation = useMutation({
    mutationFn: () => runScheduledTask(task.id),
    onSuccess: (response) => {
      pushToast({
        title: response.workflow_run_id
          ? "Schedule run submitted"
          : response.skipped
            ? "Schedule skipped"
            : "Schedule checked",
        description: response.workflow_run_id ?? (response.job_ids.length ? response.job_ids.join(", ") : undefined),
        tone: response.skipped ? "info" : "success"
      });
      invalidate();
    },
    onError: (error) => pushToast({ title: "Schedule could not run", description: error.message, tone: "error" })
  });
  const statusMutation = useMutation({
    mutationFn: (status: ScheduledTask["status"]) => updateScheduledTask(task.id, { status }),
    onSuccess: (_response, status) => {
      pushToast({
        title:
          status === "archived"
            ? "Schedule archived"
            : status === "active"
              ? "Schedule activation requested"
              : "Schedule paused",
        tone: "success"
      });
      invalidate();
    },
    onError: (error) => pushToast({ title: "Schedule could not be updated", description: error.message, tone: "error" })
  });
  const deleteMutation = useMutation({
    mutationFn: () => deleteScheduledTask(task.id),
    onSuccess: () => {
      pushToast({ title: "Schedule deleted", tone: "success" });
      invalidate();
    },
    onError: (error) => pushToast({ title: "Schedule could not be deleted", description: error.message, tone: "error" })
  });
  const busy = runMutation.isPending || statusMutation.isPending || deleteMutation.isPending;

  return (
    <article className="surface p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-sm font-semibold">{task.name}</h2>
            <Badge tone={task.status === "active" ? "success" : task.status === "blocked" ? "danger" : "muted"}>
              {task.status}
            </Badge>
            <Badge tone="default">schedule</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{scheduleSummary(task)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => runMutation.mutate()}>
            <Play className="h-4 w-4" aria-hidden="true" />
            Run
          </Button>
          {task.status === "active" ? (
            <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => statusMutation.mutate("paused")}>
              <Pause className="h-4 w-4" aria-hidden="true" />
              Pause
            </Button>
          ) : (
            <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => statusMutation.mutate("active")}>
              <Play className="h-4 w-4" aria-hidden="true" />
              Activate
            </Button>
          )}
          {task.status === "archived" ? null : (
            <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => statusMutation.mutate("archived")}>
              Archive
            </Button>
          )}
          <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => deleteMutation.mutate()}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            Delete
          </Button>
        </div>
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <Detail label="Next run" value={formatDate(task.next_run_at)} />
        <Detail label="Last run" value={formatDate(task.last_run_at)} />
        <Detail label="Latest run" value={lastRunLabel(task, lastRun)} />
      </dl>
      {task.last_error_message ? (
        <p className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          {task.last_error_message}
        </p>
      ) : null}
    </article>
  );
}

function WorkflowLimitPanel({
  jobs,
  settings,
  disabled,
  onSync
}: {
  jobs: Job[];
  settings?: SettingsResponse;
  disabled: boolean;
  onSync: (key: "max_active_one_time_tasks", value: number) => void;
}): JSX.Element {
  const runStats = workflowJobStats(jobs);

  return (
    <div className="min-w-0">
      <WorkflowLimitControl
        label="Run limit"
        value={settings?.max_active_one_time_tasks ?? 1}
        disabled={disabled || !settings}
        active={runStats.active}
        waiting={runStats.waiting}
        onSync={(value) => onSync("max_active_one_time_tasks", value)}
      />
    </div>
  );
}

function WorkflowLimitControl({
  label,
  value,
  disabled,
  active,
  waiting,
  onSync
}: {
  label: string;
  value: number;
  disabled: boolean;
  active: number;
  waiting: number;
  onSync: (value: number) => void;
}): JSX.Element {
  const initialCustomValue = value >= 6 ? value : 6;
  const [draftValue, setDraftValue] = React.useState(String(initialCustomValue));
  const [customValue, setCustomValue] = React.useState(initialCustomValue);
  const [editingCustom, setEditingCustom] = React.useState(value < 6);

  React.useEffect(() => {
    if (value >= 6) {
      setCustomValue(value);
      setDraftValue(String(value));
      setEditingCustom(false);
    }
  }, [value]);

  const parsedCustomValue = clampCustomLimit(Number(draftValue));
  const customActive = value === customValue;
  const customChanged = customValue !== value;

  function normalizeCustomEdit() {
    setCustomValue(parsedCustomValue);
    setDraftValue(String(parsedCustomValue));
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="whitespace-nowrap text-xs font-medium">{label}</span>
      <span className="whitespace-nowrap text-xs text-muted-foreground">
        {active}/{waiting}
      </span>
      <div className="flex flex-wrap items-center gap-1">
        {[1, 2, 3, 4, 5].map((item) => (
          <Button
            key={item}
            type="button"
            size="icon"
            variant={value === item ? "default" : "outline"}
            className="h-7 w-7 shrink-0 text-xs"
            disabled={disabled}
            title={`Set ${label} limit to ${item}`}
            onClick={() => {
              setDraftValue(String(item));
              onSync(item);
            }}
          >
            {item}
          </Button>
        ))}
        {editingCustom ? (
          <Input
            type="number"
            min={6}
            value={draftValue}
            disabled={disabled}
            className="h-7 w-14 px-2 text-center text-xs"
            title={`Custom ${label} limit, minimum 6`}
            onChange={(event) => setDraftValue(event.target.value)}
            onBlur={normalizeCustomEdit}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
              }
            }}
          />
        ) : (
          <Button
            type="button"
            size="sm"
            variant={customActive ? "default" : "outline"}
            className="h-7 min-w-10 shrink-0 px-2 text-xs"
            disabled={disabled}
            title={`Edit custom ${label} limit`}
            onClick={() => setEditingCustom(true)}
          >
            {customValue}
          </Button>
        )}
        <Button
          type="button"
          size="icon"
          variant={customChanged ? "default" : "outline"}
          className="h-7 w-7 shrink-0"
          disabled={disabled}
          title={`Sync ${label} limit`}
          onClick={() => {
            if (editingCustom) {
              onSync(parsedCustomValue);
              setCustomValue(parsedCustomValue);
              setDraftValue(String(parsedCustomValue));
              setEditingCustom(false);
              return;
            }
            onSync(customValue);
          }}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
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

function IconButton({
  title,
  children,
  disabled,
  onClick
}: {
  title: string;
  children: React.ReactNode;
  disabled?: boolean;
  onClick: () => void;
}): JSX.Element {
  return (
    <Button type="button" variant="outline" size="icon" title={title} aria-label={title} disabled={disabled} onClick={onClick}>
      {children}
    </Button>
  );
}

function ModuleIcon({ module }: { module: ModuleKey }): JSX.Element {
  const className = "h-4 w-4";
  if (module === "schedule") {
    return <CalendarClock className={className} aria-hidden="true" />;
  }
  if (module === "actions") {
    return <CheckCircle2 className={className} aria-hidden="true" />;
  }
  return <Wand2 className={className} aria-hidden="true" />;
}

function TagPicker({
  tags,
  selectedTags,
  search,
  open,
  onSearchChange,
  onOpenChange,
  onSelect,
  onRemove
}: {
  tags: LocalTag[];
  selectedTags: string[];
  search: string;
  open: boolean;
  onSearchChange: (value: string) => void;
  onOpenChange: (open: boolean) => void;
  onSelect: (tag: string) => void;
  onRemove: (tag: string) => void;
}): JSX.Element {
  const selectedKeys = new Set(selectedTags.map((tag) => tag.toLowerCase()));
  const query = search.trim().toLowerCase();
  const options = tags
    .filter((tag) => !selectedKeys.has(tag.name.toLowerCase()))
    .filter((tag) => !query || tag.name.toLowerCase().includes(query));
  return (
    <div className="relative">
      {selectedTags.length ? (
        <div className="mb-2 flex flex-wrap gap-2">
          {selectedTags.map((tag) => (
            <span key={tag} className="inline-flex min-h-7 max-w-full items-center gap-1 rounded-md border bg-muted px-2 text-sm">
              <span className="truncate">{tag}</span>
              <button type="button" className="text-muted-foreground hover:text-foreground" onClick={() => onRemove(tag)}>
                <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <Input
        value={search}
        placeholder="Search local tags"
        onFocus={() => onOpenChange(true)}
        onBlur={() => window.setTimeout(() => onOpenChange(false), 120)}
        onChange={(event) => onSearchChange(event.target.value)}
      />
      {open ? (
        <div className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border bg-background p-1 shadow-lg">
          {options.length ? (
            options.map((tag) => (
              <button
                key={tag.id}
                type="button"
                className="block w-full rounded-sm px-3 py-2 text-left text-sm hover:bg-muted"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => onSelect(tag.name)}
              >
                {tag.name}
              </button>
            ))
          ) : (
            <div className="px-3 py-2 text-sm text-muted-foreground">
              {tags.length ? "No matching tags" : "No local tags yet"}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

async function submitDraft(form: WorkflowForm): Promise<{ jobIds: string[] }> {
  if (form.modules.schedule) {
    const task = await createScheduledTask(workflowToScheduleRequest(form));
    return { jobIds: task.last_job_id ? [task.last_job_id] : [] };
  }
  if (form.target_type === "artists") {
    const response = await runWorkflow({ config: workflowToConfig(form) });
    return { jobIds: response.job_ids };
  }
  if (form.target_type === "artworks") {
    throw new Error("Artwork-only workflows are not available yet.");
  }
  if (form.target_type === "single_artist" && form.actions.length === 1 && form.actions[0] === "sync_artist") {
    const response = await createArtist(form.artist_id.trim());
    return { jobIds: [response.job_id] };
  }
  if (form.target_type === "single_artist" && form.actions.length === 1 && form.actions[0] === "download_artist") {
    const response = await createDownloadJob({
      user_id: form.artist_id.trim(),
      artwork_id: null,
      mode: "artist",
      force_rescan: form.force_rescan,
      retry_failed: form.actions.includes("retry_failed_artist"),
      full_download: form.download_scope === "full",
      max_artworks: numberOrNull(form.max_artworks),
      min_artwork_id: form.min_artwork_id.trim() || null,
      max_artwork_id: form.max_artwork_id.trim() || null,
      naming_rule: namingRuleOrNull(form),
      only_new_artworks: ruleOnlyNewArtworks(form),
      stop_if_artwork_count_above: ruleArtworkCountLimit(form),
      tag_variants: ruleTagVariants(form)
    });
    return { jobIds: [response.job_id] };
  }
  if (form.target_type === "single_artwork") {
    const response = await createDownloadJob({
      user_id: null,
      artwork_id: form.artwork_id.trim(),
      mode: "artwork",
      force_rescan: form.force_rescan,
      retry_failed: false,
      full_download: form.download_scope === "full",
      max_artworks: numberOrNull(form.max_artworks),
      min_artwork_id: form.min_artwork_id.trim() || null,
      max_artwork_id: form.max_artwork_id.trim() || null,
      naming_rule: namingRuleOrNull(form),
      only_new_artworks: ruleOnlyNewArtworks(form),
      stop_if_artwork_count_above: ruleArtworkCountLimit(form),
      tag_variants: ruleTagVariants(form)
    });
    return { jobIds: [response.job_id] };
  }
  const response = await runWorkflow({ config: workflowToConfig(form) });
  return { jobIds: response.job_ids };
}

function workflowToScheduleRequest(form: WorkflowForm) {
  const config = workflowToConfig(form);
  return {
    name: form.name.trim(),
    action: config.actions[0] ?? "download_artist",
    target_artist_id: scheduleTargetArtistId(form),
    interval_days: form.interval_days,
    enabled: form.enabled,
    run_after_startup: form.run_after_startup,
    config
  };
}

function workflowToConfig(form: WorkflowForm): ScheduledTaskConfig {
  return {
    target: {
      type: form.target_type as ScheduledTaskTargetType,
      artist_id: form.target_type === "single_artist" ? form.artist_id.trim() : null,
      artwork_id: form.target_type === "single_artwork" ? form.artwork_id.trim() : null,
      artist_ids: form.target_type === "artists" ? queuedArtistIds(form) : [],
      artwork_ids: form.target_type === "artists" ? queuedArtworkIds(form) : [],
      artist_source: form.target_type === "artists" ? form.artist_source : "artist_ids",
      tags: form.target_type === "artists_with_tag" ? form.tags : [],
      tag: form.target_type === "artists_with_tag" ? form.tags[0] ?? null : null,
      days: form.target_type === "artists_not_checked" ? form.stale_target_days : null
    },
    filters: [
      ...(form.modules.filters && form.filters.last_checked_before_days
        ? [{ type: "last_checked_before_days" as const, days: form.stale_filter_days }]
        : []),
      ...(form.modules.filters && form.filters.has_failed_files
        ? [{ type: "has_failed_files" as const, days: null }]
        : [])
    ],
    actions: workflowActionsForSchedule(form),
    download_options: {
      full_download: form.modules.options && form.download_scope === "full",
      max_artworks: form.modules.filters ? numberOrNull(form.max_artworks) : null,
      min_artwork_id: form.modules.filters ? form.min_artwork_id.trim() || null : null,
      max_artwork_id: form.modules.filters ? form.max_artwork_id.trim() || null : null,
      naming_rule: namingRuleOrNull(form),
      only_new_artworks: ruleOnlyNewArtworks(form),
      stop_if_artwork_count_above: ruleArtworkCountLimit(form),
      tag_variants: ruleTagVariants(form)
    },
    max_artists_per_run: form.max_artists_per_run,
    artist_selection: form.artist_selection,
    skip_unavailable_artists: form.skip_unavailable_artists
  };
}

function workflowActionsForSchedule(form: WorkflowForm): ScheduledTaskAction[] {
  if (form.target_type === "single_artwork" || form.target_type === "artworks") {
    return ["download_artist"];
  }
  return form.actions;
}

function validateForm(form: WorkflowForm): string[] {
  const errors: string[] = [];
  if (form.target_type === "artists") {
    const ids = [...queuedArtistIds(form), ...queuedArtworkIds(form)];
    if (!ids.length) {
      errors.push("Add at least one artist target ID.");
    }
    for (const item of ids) {
      if (!/^\d+$/.test(item)) {
        errors.push("Artist target IDs must contain digits only.");
        break;
      }
    }
  }
  if (form.target_type === "artworks") {
    errors.push("Artwork-only workflows are not available yet.");
  }
  if (form.target_type === "single_artist" && !/^\d+$/.test(form.artist_id.trim())) {
    errors.push("Artist ID must contain digits only.");
  }
  if (form.target_type === "single_artwork" && !/^\d+$/.test(form.artwork_id.trim())) {
    errors.push("Artwork ID must contain digits only.");
  }
  if (form.target_type === "artists_with_tag" && form.tags.length === 0) {
    errors.push("Select at least one local tag.");
  }
  if (!form.actions.length) {
    errors.push("Select at least one action.");
  }
  if (!Number.isInteger(form.max_artists_per_run) || form.max_artists_per_run < 1) {
    errors.push("Max targets per run must be at least 1.");
  }
  if (form.modules.schedule && (!Number.isInteger(form.interval_days) || form.interval_days < 1)) {
    errors.push("Interval days must be at least 1.");
  }
  if (!form.modules.schedule && form.target_type === "single_artist" && form.actions.length > 1) {
    errors.push("One-off single-artist drafts currently run one action at a time.");
  }
  if (!form.modules.schedule && form.target_type === "single_artwork" && form.actions.some((action) => action !== "download_artist")) {
    errors.push("Artwork drafts only support download.");
  }
  for (const [label, value] of [
    ["Max artworks", form.max_artworks],
    ["Artwork ID from", form.min_artwork_id],
    ["Artwork ID to", form.max_artwork_id],
    ["Artwork count limit", form.rules.artwork_count_limit]
  ] as const) {
    if (value.trim() && !/^\d+$/.test(value.trim())) {
      errors.push(`${label} must contain digits only.`);
    }
  }
  if (form.modules.rule && form.rules.stop_if_artwork_count_above && !form.rules.artwork_count_limit.trim()) {
    errors.push("Artwork count limit is required.");
  }
  if (form.modules.rule && form.rules.tag_variant_enabled && !form.rules.tag_variant_tag.trim()) {
    errors.push("Variant matching tag is required.");
  }
  return errors;
}

function workflowRunGroups(runs: WorkflowBatchRun[]): {
  active: WorkflowBatchRun[];
  failed: WorkflowBatchRun[];
  completed: WorkflowBatchRun[];
} {
  return {
    active: runs.filter((run) => run.status === "running"),
    failed: runs.filter((run) => run.status === "failed" || run.status === "partial"),
    completed: runs.filter((run) => run.status === "completed" || run.status === "skipped")
  };
}

function emptyRunGroups(): {
  active: WorkflowBatchRun[];
  failed: WorkflowBatchRun[];
  completed: WorkflowBatchRun[];
} {
  return { active: [], failed: [], completed: [] };
}

function workflowScheduleGroups(tasks: ScheduledTask[]): {
  active: ScheduledTask[];
  blocked: ScheduledTask[];
  inactive: ScheduledTask[];
  archived: ScheduledTask[];
} {
  return {
    active: tasks.filter((task) => task.status === "active"),
    blocked: tasks.filter((task) => task.status === "blocked"),
    inactive: tasks.filter((task) => task.status === "paused" || task.status === "inactive"),
    archived: tasks.filter((task) => task.status === "archived")
  };
}

function workflowWaitingJobs(jobs: Job[]): Job[] {
  return jobs.filter((job) => job.options.activation_scope === "one_time" && job.status === "inactive");
}

function filterWorkflowRuns(runs: WorkflowBatchRun[], search: string): WorkflowBatchRun[] {
  const query = normalizeSearch(search);
  if (!query) {
    return runs;
  }
  return runs.filter((run) =>
    searchableText([
      run.id,
      run.status,
      run.source,
      run.failure_reason,
      run.items.flatMap((item) => [
        item.title,
        item.draft_id,
        item.status,
        item.failure_reason,
        item.error_message,
        item.job_ids.join(" ")
      ]).join(" ")
    ]).includes(query)
  );
}

function filterSchedules(tasks: ScheduledTask[], search: string): ScheduledTask[] {
  const query = normalizeSearch(search);
  if (!query) {
    return tasks;
  }
  return tasks.filter((task) =>
    searchableText([
      task.name,
      task.status,
      task.action,
      task.target_artist_id,
      task.failure_reason,
      task.last_error_code,
      task.last_error_message,
      scheduleSummary(task)
    ]).includes(query)
  );
}

function filterWaitingJobs(jobs: Job[], search: string): Job[] {
  const query = normalizeSearch(search);
  if (!query) {
    return jobs;
  }
  return jobs.filter((job) =>
    searchableText([
      job.id,
      job.status,
      job.type,
      job.workflow_source,
      job.input_user_id,
      job.input_artwork_id,
      job.error_message,
      jobTarget(job)
    ]).includes(query)
  );
}

function normalizeSearch(value: string): string {
  return value.trim().toLowerCase();
}

function searchableText(values: unknown[]): string {
  return values.filter(Boolean).join(" ").toLowerCase();
}

function runJobIds(run: WorkflowBatchRun | null): string[] {
  if (!run) {
    return [];
  }
  return Array.from(new Set(run.items.flatMap((item) => item.job_ids)));
}

function groupRunsByFailureReason(runs: WorkflowBatchRun[]): Array<{ reason: string; items: WorkflowBatchRun[] }> {
  return groupedByReason(runs, (run) => run.failure_reason || "unknown");
}

function groupSchedulesByFailureReason(tasks: ScheduledTask[]): Array<{ reason: string; items: ScheduledTask[] }> {
  return groupedByReason(tasks, (task) => task.failure_reason || "unknown");
}

function groupedByReason<T>(items: T[], reasonFor: (item: T) => string): Array<{ reason: string; items: T[] }> {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const reason = reasonFor(item);
    groups.set(reason, [...(groups.get(reason) ?? []), item]);
  }
  return Array.from(groups.entries()).map(([reason, groupedItems]) => ({ reason, items: groupedItems }));
}

function invalidateRuntimeQueries(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  void queryClient.invalidateQueries({ queryKey: ["scheduled-tasks"] });
  void queryClient.invalidateQueries({ queryKey: ["workflow-runs"] });
}

function loadStoredDrafts(): DraftWorkflow[] {
  try {
    const text = window.localStorage.getItem(draftsStorageKey);
    if (!text) {
      return [];
    }
    const parsed = JSON.parse(text) as DraftWorkflow[];
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter((draft) => draft && typeof draft.id === "string" && draft.form)
      .map((draft) => ({
        ...draft,
        form: normalizeStoredForm(draft.form)
      }));
  } catch {
    return [];
  }
}

function normalizeStoredForm(form: WorkflowForm): WorkflowForm {
  const modules = { ...initialForm.modules, ...form.modules };
  const legacyModules = modules as Record<string, boolean>;
  if (legacyModules.advanced) {
    modules.rule = true;
  }
  const legacyRules = form.rules as RuleConfig & { tag_variant_action?: WorkflowAction };
  const targetType = form.target_type === "single_artist" || form.target_type === "single_artwork" ? "artists" : form.target_type;
  const artistSource = form.target_type === "single_artwork" ? "artwork_ids" : form.artist_source ?? "artist_ids";
  const artistIds = normalizeNumericIds([
    ...(form.artist_ids ?? []),
    ...(form.target_type === "single_artist" && form.artist_id ? [form.artist_id] : [])
  ]);
  const artworkIds = normalizeNumericIds([
    ...(form.artwork_ids ?? []),
    ...(form.target_type === "single_artwork" && form.artwork_id ? [form.artwork_id] : [])
  ]);
  return {
    ...initialForm,
    ...form,
    target_type: targetType,
    artist_source: artistSource,
    artist_ids: artistIds,
    artwork_ids: artworkIds,
    actions: form.actions,
    modules,
    naming_rule: form.naming_rule || defaultNamingRule,
    rules: {
      ...initialForm.rules,
      ...form.rules,
      tag_variant_behavior:
        form.rules.tag_variant_behavior ?? legacyActionToBehavior(legacyRules.tag_variant_action)
    }
  };
}

function previewText(form: WorkflowForm): string {
  const mode = form.modules.schedule ? `every ${form.interval_days} days` : "staged";
  const actions = form.actions.map((action) => actionLabels[action]).join(" then ");
  const scope = form.actions.includes("retry_failed_artist")
    ? "failed files only"
    : form.download_scope === "full"
      ? "all discovered works"
      : "new works only";
  const rules = ruleSummary(form);
  return `${targetDetail(form)}, ${actions}, ${scope}, ${mode}${rules ? `, ${rules}` : ""}.`;
}

function ruleSummary(form: WorkflowForm): string {
  if (!form.modules.rule) {
    return "";
  }
  const rules: string[] = [];
  if (form.rules.only_new_artworks) {
    rules.push("only with new works");
  }
  if (form.rules.stop_if_artwork_count_above && form.rules.artwork_count_limit.trim()) {
    rules.push(`stop above ${form.rules.artwork_count_limit.trim()} works`);
  }
  if (form.rules.skip_if_last_run_failed) {
    rules.push("skip after failed run");
  }
  if (form.rules.tag_variant_enabled && form.rules.tag_variant_tag.trim()) {
    rules.push(`${tagVariantBehaviorLabels[form.rules.tag_variant_behavior]} for ${form.rules.tag_variant_tag.trim()}`);
  }
  return rules.join(", ");
}

function previewNamingRule(rule: string): string {
  return rule
    .replaceAll("{artist}", "Artist")
    .replaceAll("{artist_id}", "123456")
    .replaceAll("{artwork_id}", "987654321")
    .replaceAll("{title}", "Artwork title")
    .replaceAll("{page}", "0")
    .replaceAll("{original_filename}", "987654321_p0.jpg")
    .replaceAll("{ext}", "jpg")
    .replaceAll("{type}", "illust")
    .replaceAll("{download_date}", "2026-06-28")
    .replaceAll("{ai}", "AI");
}

function namingRuleOrNull(form: WorkflowForm): string | null {
  if (!form.modules.naming) {
    return null;
  }
  const rule = form.naming_rule.trim();
  return rule && rule !== defaultNamingRule ? rule : null;
}

function appendNumericIds(ids: string[], value: string): string[] {
  return normalizeNumericIds([...ids, ...value.split(/[,\s]+/)]);
}

function normalizeNumericIds(ids: string[]): string[] {
  const normalized: string[] = [];
  const seen = new Set<string>();
  for (const rawId of ids) {
    const id = String(rawId).trim();
    if (!id || seen.has(id)) {
      continue;
    }
    normalized.push(id);
    seen.add(id);
  }
  return normalized;
}

function activeArtistTargetIds(form: WorkflowForm): string[] {
  return form.artist_source === "artist_ids" ? form.artist_ids : form.artwork_ids;
}

function activeArtistTargetInput(form: WorkflowForm): string {
  return form.artist_source === "artist_ids" ? form.artist_id_input : form.artwork_id_input;
}

function artistTargetIds(form: WorkflowForm): string[] {
  return appendNumericIds(activeArtistTargetIds(form), activeArtistTargetInput(form));
}

function queuedArtistIds(form: WorkflowForm): string[] {
  return appendNumericIds(form.artist_ids, form.artist_source === "artist_ids" ? form.artist_id_input : "");
}

function queuedArtworkIds(form: WorkflowForm): string[] {
  return appendNumericIds(form.artwork_ids, form.artist_source === "artwork_ids" ? form.artwork_id_input : "");
}

function scheduleTargetArtistId(form: WorkflowForm): string | null {
  if (form.target_type === "single_artist") {
    return form.artist_id.trim();
  }
  if (form.target_type === "artists" && form.artist_source === "artist_ids") {
    return queuedArtistIds(form)[0] ?? null;
  }
  return null;
}

function ruleOnlyNewArtworks(form: WorkflowForm): boolean {
  return form.modules.rule && form.rules.only_new_artworks;
}

function ruleArtworkCountLimit(form: WorkflowForm): number | null {
  if (!form.modules.rule || !form.rules.stop_if_artwork_count_above) {
    return null;
  }
  return numberOrNull(form.rules.artwork_count_limit);
}

function ruleTagVariants(form: WorkflowForm): Array<Record<string, string>> {
  if (!form.modules.rule || !form.rules.tag_variant_enabled) {
    return [];
  }
  const tag = form.rules.tag_variant_tag.trim();
  const namingRule = form.rules.tag_variant_naming_rule.trim();
  if (!tag) {
    return [];
  }
  return [
    {
      tag,
      behavior: form.rules.tag_variant_behavior,
      ...(namingRule ? { naming_rule: namingRule } : {})
    }
  ];
}

function legacyActionToBehavior(action: WorkflowAction | undefined): TagVariantBehavior {
  if (action === "retry_failed_artist") {
    return "retry_failed";
  }
  if (action === "sync_artist") {
    return "skip";
  }
  return "download";
}

function lastRunItemStatus(draftId: string, runs: WorkflowBatchRun[]): WorkflowBatchRunItem["status"] | null {
  for (const run of runs) {
    const item = run.items.find((entry) => entry.draft_id === draftId);
    if (item) {
      return item.status;
    }
  }
  return null;
}

function draftTitle(form: WorkflowForm): string {
  return form.name.trim() || `${form.modules.schedule ? "Schedule" : "Workflow"}: ${targetLabels[form.target_type]}`;
}

function scheduleSummary(task: ScheduledTask): string {
  const target = targetLabels[task.config.target.type as WorkflowTarget] ?? task.config.target.type;
  const actions = task.config.actions.map((action) => actionLabels[action as WorkflowAction] ?? action).join(" then ");
  return `${target} · ${actions} · every ${task.interval_days} days`;
}

function targetDetail(form: WorkflowForm): string {
  if (form.target_type === "artists") {
    const artistCount = queuedArtistIds(form).length;
    const artworkCount = queuedArtworkIds(form).length;
    return `Artists from ${artistCount} artist IDs, ${artworkCount} artwork IDs`;
  }
  if (form.target_type === "artworks") {
    return "Artworks placeholder";
  }
  if (form.target_type === "single_artist") {
    return `Artist ${form.artist_id || "-"}`;
  }
  if (form.target_type === "single_artwork") {
    return `Artwork ${form.artwork_id || "-"}`;
  }
  if (form.target_type === "artists_with_tag") {
    return `Tags ${form.tags.join(", ") || "-"}`;
  }
  if (form.target_type === "artists_not_checked") {
    return `Not checked for ${form.stale_target_days} days`;
  }
  return "All artists";
}

function latestScheduleRun(task: ScheduledTask, runs: WorkflowBatchRun[]): WorkflowBatchRun | null {
  const summaryRunId = task.last_run_summary?.workflow_run_id;
  const matchedBySummary = typeof summaryRunId === "string" ? runs.find((run) => run.id === summaryRunId) : null;
  if (matchedBySummary) {
    return matchedBySummary;
  }
  return runs.find((run) => run.schedule_id === task.id) ?? null;
}

function lastRunLabel(task: ScheduledTask, run: WorkflowBatchRun | null): string {
  if (run) {
    return `${run.status} · ${run.completed}/${run.total}`;
  }
  const summaryRunId = task.last_run_summary?.workflow_run_id;
  if (typeof summaryRunId === "string") {
    return summaryRunId;
  }
  const count = task.last_run_summary?.created_jobs;
  return typeof count === "number" ? String(count) : task.last_job_id ?? "-";
}

function workflowJobStats(jobs: Job[]): { active: number; waiting: number } {
  const oneTimeJobs = jobs.filter((job) => job.options.activation_scope === "one_time");
  return {
    active: oneTimeJobs.filter((job) => job.status === "queued" || job.status === "running").length,
    waiting: oneTimeJobs.filter((job) => job.status === "inactive").length
  };
}

function jobLabel(job: Job): string {
  return job.type.replaceAll("_", " ");
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

function sourceLabel(source: string): string {
  if (source === "manual_schedule" || source === "schedule") {
    return "schedule";
  }
  if (source === "workflow_batch") {
    return "manual";
  }
  if (source.includes("shortcut")) {
    return "shortcut";
  }
  return source.replaceAll("_", " ");
}

function runTitle(run: WorkflowBatchRun): string {
  if (run.items.length === 1) {
    return run.items[0].title;
  }
  return `${run.items.length} workflow item run`;
}

function WorkflowRunStatusPill({ status }: { status: WorkflowBatchRun["status"] }): JSX.Element {
  return <Badge tone={workflowRunTone(status)}>{status}</Badge>;
}

function workflowRunTone(status: WorkflowBatchRun["status"]): "default" | "success" | "danger" | "warning" | "muted" {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed" || status === "partial") {
    return "danger";
  }
  if (status === "running") {
    return "default";
  }
  return "muted";
}

function workflowItemTone(status: WorkflowBatchRunItem["status"]): "default" | "success" | "danger" | "warning" | "muted" {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed") {
    return "danger";
  }
  if (status === "running" || status === "pending") {
    return "default";
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
  return "muted";
}

function Detail({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <dt className="text-xs uppercase text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words font-medium">{value}</dd>
    </div>
  );
}

function toggleItem<T>(items: T[], item: T, checked: boolean): T[] {
  if (checked) {
    return items.includes(item) ? items : [...items, item];
  }
  return items.filter((value) => value !== item);
}

function isMultiArtistTarget(target: WorkflowTarget): boolean {
  return target === "all_artists" || target === "artists_with_tag" || target === "artists_not_checked";
}

function numberOrNull(value: string): number | null {
  const text = value.trim();
  return text ? Number(text) : null;
}

function clampConcurrency(value: number): number {
  if (!Number.isFinite(value)) {
    return 1;
  }
  return Math.max(1, Math.floor(value));
}

function clampCustomLimit(value: number): number {
  if (!Number.isFinite(value)) {
    return 6;
  }
  return Math.max(6, Math.floor(value));
}
