import * as React from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  CheckCircle2,
  Copy,
  ListPlus,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  Wand2,
  XCircle
} from "lucide-react";

import { createArtist, listLocalTags, type LocalTag } from "@/api/artists";
import { createDownloadJob } from "@/api/downloads";
import { listJobs, type Job } from "@/api/jobs";
import {
  createScheduledTask,
  listScheduledTasks,
  type ScheduledTask,
  type ScheduledTaskAction,
  type ScheduledTaskArtistSelection,
  type ScheduledTaskConfig,
  type ScheduledTaskTargetType
} from "@/api/scheduledTasks";
import { runWorkflow } from "@/api/workflows";
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

type WorkflowTab = "active" | "inactive" | "failed" | "completed";
type ModuleKey = "schedule" | "target" | "filters" | "actions" | "options" | "naming" | "rule";
type WorkflowTarget =
  | "single_artist"
  | "single_artwork"
  | "all_artists"
  | "artists_with_tag"
  | "artists_not_checked";
type WorkflowAction = "download_artist" | "sync_artist" | "retry_failed_artist";
type DownloadScope = "incremental" | "full";

type RuleConfig = {
  only_new_artworks: boolean;
  stop_if_artwork_count_above: boolean;
  artwork_count_limit: string;
  skip_if_last_run_failed: boolean;
  tag_variant_enabled: boolean;
  tag_variant_tag: string;
  tag_variant_action: WorkflowAction;
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

type WorkflowBatchItem = {
  draftId: string;
  title: string;
  status: "completed" | "failed" | "skipped";
  jobIds: string[];
  error?: string;
};

type WorkflowBatch = {
  id: string;
  createdAt: string;
  total: number;
  completed: number;
  failed: number;
  skipped: number;
  concurrency: number;
  items: WorkflowBatchItem[];
};

const requiredModules: ModuleKey[] = ["target", "actions"];
const moduleOrder: ModuleKey[] = ["schedule", "target", "filters", "actions", "options", "naming", "rule"];
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
  target_type: "single_artist",
  artist_id: "",
  artwork_id: "",
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
    tag_variant_action: "download_artist",
    tag_variant_naming_rule: "{artist}-{artist_id}/{ai}/{original_filename}"
  }
};

const tabItems: Array<{ value: WorkflowTab; label: string }> = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "failed", label: "Failed" },
  { value: "completed", label: "Completed" }
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

const targetLabels: Record<WorkflowTarget, string> = {
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
  const [tab, setTab] = React.useState<WorkflowTab>("active");
  const [tagSearch, setTagSearch] = React.useState("");
  const [tagPickerOpen, setTagPickerOpen] = React.useState(false);
  const [oneOffConcurrency, setOneOffConcurrency] = React.useState(1);
  const [batches, setBatches] = React.useState<WorkflowBatch[]>([]);

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
  const localTags = useQuery({ queryKey: ["local-tags"], queryFn: listLocalTags });

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
    mutationFn: async (request: { items: DraftWorkflow[]; concurrency: number }) => {
      const items = await runDraftBatch(request.items, request.concurrency, batches);
      return {
        id: crypto.randomUUID(),
        createdAt: new Date().toISOString(),
        total: request.items.length,
        completed: items.filter((item) => item.status === "completed").length,
        failed: items.filter((item) => item.status === "failed").length,
        skipped: items.filter((item) => item.status === "skipped").length,
        concurrency: request.concurrency,
        items
      } satisfies WorkflowBatch;
    },
    onSuccess: (batch) => {
      const ids = new Set(
        batch.items.filter((item) => item.status === "completed").map((item) => item.draftId)
      );
      setDrafts((current) => current.filter((item) => !ids.has(item.id)));
      setSelectedDraftId(null);
      setBatches((current) => [batch, ...current].slice(0, 5));
      pushToast({
        title: "Draft queue submitted",
        description: `${batch.completed}/${batch.total} completed, ${batch.skipped} skipped`,
        tone: batch.failed ? "error" : "success"
      });
      invalidateRuntimeQueries(queryClient);
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

  const visible = splitWorkflows(jobs.data?.items ?? [], schedules.data?.items ?? [], tab);

  return (
    <>
      <PageHeader
        title="Workflows"
        description="Stage workflow drafts, then submit them into jobs or schedules."
        actions={
          <>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                void jobs.refetch();
                void schedules.refetch();
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
                onClick={() => runAllMutation.mutate({ items: drafts, concurrency: oneOffConcurrency })}
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
            <div className="mt-3 rounded-md border bg-muted/20 p-3">
              <Field label="One-off workflow concurrency">
                <Input
                  type="number"
                  min={1}
                  max={6}
                  value={oneOffConcurrency}
                  onChange={(event) => setOneOffConcurrency(clampConcurrency(Number(event.target.value)))}
                />
              </Field>
              <p className="mt-2 text-xs text-muted-foreground">
                Scheduled drafts are created immediately; one-off drafts are submitted in parallel up to this limit.
              </p>
            </div>
          </section>

          {batches.length ? (
            <section className="surface p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold">Run Batches</h2>
                  <p className="mt-1 text-sm text-muted-foreground">Recent Run All submissions</p>
                </div>
              </div>
              <div className="mt-4 space-y-3">
                {batches.map((batch) => (
                  <BatchSummary key={batch.id} batch={batch} />
                ))}
              </div>
            </section>
          ) : null}

          {selectedDraft ? (
            <DraftDetail draft={selectedDraft} onEdit={() => openEditBuilder(selectedDraft)} />
          ) : (
            <DataState title="No draft selected" description="Draft details appear here." />
          )}
        </aside>

        <section className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Tabs value={tab} onValueChange={setTab} items={tabItems} />
            <p className="text-sm text-muted-foreground">{visible.length} submitted item(s)</p>
          </div>
          {jobs.isError ? (
            <DataState title="Could not load jobs" description={jobs.error.message} variant="error" />
          ) : schedules.isError ? (
            <DataState title="Could not load workflows" description={schedules.error.message} variant="error" />
          ) : jobs.isLoading || schedules.isLoading ? (
            <DataState title="Loading submitted workflows" variant="loading" />
          ) : visible.length === 0 ? (
            <DataState title="No submitted workflows here" description="Submit a draft or choose another tab." />
          ) : (
            <div className="grid gap-3">
              {visible.map((item) =>
                item.kind === "schedule" ? (
                  <ScheduleWorkflowCard key={`schedule-${item.task.id}`} task={item.task} />
                ) : (
                  <JobWorkflowCard key={`job-${item.job.id}`} job={item.job} />
                )
              )}
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
                <p className="rounded-md border border-amber-500/30 bg-amber-50 p-3 text-sm text-amber-800">
                  Full download schedules re-check already tracked works every run.
                </p>
              ) : null}
            </aside>
          </div>
        </form>
      </Dialog>
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
          {(Object.keys(targetLabels) as WorkflowTarget[]).map((target) => (
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
                  actions: target === "single_artwork" ? ["download_artist"] : form.actions
                })
              }
            >
              {targetLabels[target]}
            </button>
          ))}
        </div>
      </div>
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
          <Field label="Max artists per run">
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
  const artworkTarget = form.target_type === "single_artwork";
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
      <p className="text-sm text-muted-foreground">Existing file handling still follows Settings for skip existing files.</p>
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
        Run naming/action variant when tag matches
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
          <Field label="Variant action">
            <Select
              value={form.rules.tag_variant_action}
              onChange={(event) =>
                setForm({
                  ...form,
                  rules: { ...form.rules, tag_variant_action: event.target.value as WorkflowAction }
                })
              }
            >
              {Object.entries(actionLabels).map(([value, label]) => (
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

function BatchSummary({ batch }: { batch: WorkflowBatch }): JSX.Element {
  return (
    <article className="rounded-md border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">{formatDate(batch.createdAt)}</h3>
          <p className="mt-1 text-xs text-muted-foreground">Concurrency {batch.concurrency}</p>
        </div>
        <Badge tone={batch.failed ? "danger" : batch.skipped ? "muted" : "success"}>
          {batch.completed}/{batch.total}
        </Badge>
      </div>
      <div className="mt-3 space-y-2">
        {batch.items.map((item) => (
          <div key={item.draftId} className="rounded-md border bg-muted/20 p-2 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{item.title}</span>
              <Badge tone={item.status === "completed" ? "success" : item.status === "skipped" ? "muted" : "danger"}>
                {item.status}
              </Badge>
            </div>
            {item.jobIds.length ? (
              <p className="mt-1 break-all text-muted-foreground">{item.jobIds.length} job(s): {item.jobIds.join(", ")}</p>
            ) : item.error ? (
              <p className="mt-1 break-words text-destructive">{item.error}</p>
            ) : (
              <p className="mt-1 text-muted-foreground">No job was created.</p>
            )}
          </div>
        ))}
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

function ScheduleWorkflowCard({ task }: { task: ScheduledTask }): JSX.Element {
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
        <Button type="button" size="sm" variant="outline" asChild>
          <Link to="/jobs/schedules">Manage</Link>
        </Button>
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <Detail label="Next run" value={formatDate(task.next_run_at)} />
        <Detail label="Last run" value={formatDate(task.last_run_at)} />
        <Detail label="Last jobs" value={lastJobCount(task)} />
      </dl>
    </article>
  );
}

function JobWorkflowCard({ job }: { job: Job }): JSX.Element {
  return (
    <article className="surface p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-sm font-semibold">{jobLabel(job)}</h2>
            <StatusPill status={job.status} />
            <Badge tone="muted">one-off</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{jobTarget(job)}</p>
        </div>
        <Button type="button" size="sm" variant="outline" asChild>
          <Link to={`/jobs?job=${job.id}`}>Inspect</Link>
        </Button>
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-4">
        <Detail label="Created" value={formatDate(job.created_at)} />
        <Detail label="Started" value={formatDate(job.started_at)} />
        <Detail label="Finished" value={formatDate(job.finished_at)} />
        <Detail label="Files" value={`${job.completed_files}/${job.total_files || 0}`} />
      </dl>
      {job.error_message ? (
        <p className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          {job.error_message}
        </p>
      ) : null}
    </article>
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
      naming_tag_variants: ruleNamingVariants(form)
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
      naming_tag_variants: ruleNamingVariants(form)
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
    target_artist_id: form.target_type === "single_artist" ? form.artist_id.trim() : null,
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
      tag_variant_action: ruleTagVariantAction(form),
      naming_tag_variants: ruleNamingVariants(form)
    },
    max_artists_per_run: form.max_artists_per_run,
    artist_selection: form.artist_selection,
    skip_unavailable_artists: form.skip_unavailable_artists
  };
}

function workflowActionsForSchedule(form: WorkflowForm): ScheduledTaskAction[] {
  if (form.target_type === "single_artwork") {
    return ["download_artist"];
  }
  return form.actions;
}

function validateForm(form: WorkflowForm): string[] {
  const errors: string[] = [];
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
    errors.push("Max artists per run must be at least 1.");
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

function splitWorkflows(
  jobs: Job[],
  tasks: ScheduledTask[],
  tab: WorkflowTab
): Array<{ kind: "job"; job: Job } | { kind: "schedule"; task: ScheduledTask }> {
  if (tab === "active") {
    return [
      ...tasks.filter((task) => task.status === "active").map((task) => ({ kind: "schedule" as const, task })),
      ...jobs.filter((job) => job.status === "queued" || job.status === "running").map((job) => ({ kind: "job" as const, job }))
    ];
  }
  if (tab === "inactive") {
    return tasks.filter((task) => task.status === "paused").map((task) => ({ kind: "schedule" as const, task }));
  }
  if (tab === "failed") {
    return [
      ...tasks.filter((task) => task.status === "blocked").map((task) => ({ kind: "schedule" as const, task })),
      ...jobs.filter((job) => job.status === "failed" || job.status === "cancelled").map((job) => ({ kind: "job" as const, job }))
    ];
  }
  return jobs.filter((job) => job.status === "completed").map((job) => ({ kind: "job" as const, job }));
}

function invalidateRuntimeQueries(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  void queryClient.invalidateQueries({ queryKey: ["scheduled-tasks"] });
}

async function runDraftBatch(
  drafts: DraftWorkflow[],
  concurrency: number,
  previousBatches: WorkflowBatch[]
): Promise<WorkflowBatchItem[]> {
  const results: WorkflowBatchItem[] = [];
  let nextIndex = 0;
  const workerCount = Math.min(clampConcurrency(concurrency), drafts.length);
  async function runNext(): Promise<void> {
    const index = nextIndex;
    nextIndex += 1;
    const draft = drafts[index];
    if (!draft) {
      return;
    }
    if (draft.form.modules.rule && draft.form.rules.skip_if_last_run_failed && lastBatchStatus(draft.id, previousBatches) === "failed") {
      results[index] = {
        draftId: draft.id,
        title: draftTitle(draft.form),
        status: "skipped",
        jobIds: [],
        error: "Skipped because the last run failed"
      };
      await runNext();
      return;
    }
    try {
      const response = await submitDraft(draft.form);
      results[index] = {
        draftId: draft.id,
        title: draftTitle(draft.form),
        status: "completed",
        jobIds: response.jobIds
      };
    } catch (error) {
      results[index] = {
        draftId: draft.id,
        title: draftTitle(draft.form),
        status: "failed",
        jobIds: [],
        error: error instanceof Error ? error.message : "Workflow failed"
      };
    }
    await runNext();
  }
  await Promise.all(Array.from({ length: workerCount }, () => runNext()));
  return results;
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
  return {
    ...initialForm,
    ...form,
    modules,
    naming_rule: form.naming_rule || defaultNamingRule,
    rules: { ...initialForm.rules, ...form.rules }
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
  return `${targetLabels[form.target_type]}, ${actions}, ${scope}, ${mode}${rules ? `, ${rules}` : ""}.`;
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
    rules.push(`variant for ${form.rules.tag_variant_tag.trim()}`);
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

function ruleOnlyNewArtworks(form: WorkflowForm): boolean {
  return form.modules.rule && form.rules.only_new_artworks;
}

function ruleArtworkCountLimit(form: WorkflowForm): number | null {
  if (!form.modules.rule || !form.rules.stop_if_artwork_count_above) {
    return null;
  }
  return numberOrNull(form.rules.artwork_count_limit);
}

function ruleTagVariantAction(form: WorkflowForm): string | null {
  if (!form.modules.rule || !form.rules.tag_variant_enabled || !form.rules.tag_variant_tag.trim()) {
    return null;
  }
  return form.rules.tag_variant_action;
}

function ruleNamingVariants(form: WorkflowForm): Array<Record<string, string>> {
  if (!form.modules.rule || !form.rules.tag_variant_enabled) {
    return [];
  }
  const tag = form.rules.tag_variant_tag.trim();
  const namingRule = form.rules.tag_variant_naming_rule.trim();
  if (!tag || !namingRule) {
    return [];
  }
  return [{ tag, naming_rule: namingRule }];
}

function lastBatchStatus(draftId: string, batches: WorkflowBatch[]): WorkflowBatchItem["status"] | null {
  for (const batch of batches) {
    const item = batch.items.find((entry) => entry.draftId === draftId);
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

function lastJobCount(task: ScheduledTask): string {
  const count = task.last_run_summary?.created_jobs;
  return typeof count === "number" ? String(count) : task.last_job_id ?? "-";
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

function StatusPill({ status }: { status: Job["status"] }): JSX.Element {
  const tone =
    status === "completed"
      ? "success"
      : status === "failed" || status === "cancelled"
        ? "danger"
        : status === "running"
          ? "default"
          : "muted";
  return <Badge tone={tone}>{status}</Badge>;
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
  return Math.max(1, Math.min(6, Math.floor(value)));
}
