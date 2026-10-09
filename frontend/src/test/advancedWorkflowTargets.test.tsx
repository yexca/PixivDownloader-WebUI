import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as workflows from "@/api/workflows";
import type { WorkflowDefinition, WorkflowRun } from "@/api/workflows";
import { AdvancedWorkflowBuilder } from "@/components/workflows/AdvancedWorkflowBuilder";
import { ToastProvider } from "@/components/ToastProvider";

function builder(definition?: WorkflowDefinition) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider><AdvancedWorkflowBuilder definition={definition} /></ToastProvider>
    </QueryClientProvider>
  );
  return client;
}

function savedDefinition(config: Record<string, unknown>): WorkflowDefinition {
  return {
    id: "saved", name: "Saved workflow", triggers: [], created_at: null, updated_at: null,
    definition: { name: "Saved workflow", metadata: { legacy: true }, nodes: [
      { id: "legacy-target", type: "artist_target", title: "Original target", config }
    ] }
  };
}

function mockSave(definition: WorkflowDefinition) {
  return vi.spyOn(workflows, "saveWorkflowDefinition").mockResolvedValue({ definition, trigger: null, run: null });
}

function inputValue(label: string): string {
  return (screen.getByLabelText(label) as HTMLInputElement).value;
}

describe("advanced workflow target protocol", () => {
  it.each([
    ["all", "all", "all_artists"],
    ["all_artists", "all", "all_artists"],
    ["tagged", "tagged", "artists_with_tag"],
    ["artists_with_tag", "tagged", "artists_with_tag"],
    ["stale", "stale", "artists_not_checked"],
    ["artists_not_checked", "stale", "artists_not_checked"]
  ])("preserves %s definition parameters while canonicalizing its bulk scope", async (stored, ui, canonical) => {
    const definition: WorkflowDefinition = {
      id: "saved", name: "Saved workflow", triggers: [], created_at: null, updated_at: null,
      definition: { nodes: [{ id: "target", type: "artist_target", config: {
        scope: stored, tag: "chosen", artist_ids: ["unused"], artwork_ids: ["unused"],
        ...(stored === "stale" ? { stale_days: 7 } : { days: 7 }), max_artists: 19
      } }] }
    };
    const save = vi.spyOn(workflows, "saveWorkflowDefinition").mockResolvedValue({ definition, trigger: null, run: null });
    const client = builder(definition);
    expect((screen.getByLabelText("Artist scope") as HTMLSelectElement).value).toBe(ui);
    if (ui === "tagged") expect((screen.getByLabelText("Local tag") as HTMLInputElement).value).toBe("chosen");
    if (ui === "stale") expect((screen.getByLabelText("Not checked for days") as HTMLInputElement).value).toBe("7");
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].definition.nodes[0].config).toEqual({
      ...(definition.definition.nodes as Array<{ config: Record<string, unknown> }>)[0].config, scope: canonical
    });
    client.clear();
  });

  it.each([
    ["all", "all_artists"], ["tagged", "artists_with_tag"], ["stale", "artists_not_checked"]
  ])("runs %s without values left in other scope fields", async (scope, canonical) => {
    const run = vi.spyOn(workflows, "createAdvancedWorkflowRun").mockResolvedValue({ id: "run" } as WorkflowRun);
    const client = builder();
    fireEvent.change(screen.getByLabelText("Artist IDs"), { target: { value: "999" } });
    fireEvent.change(screen.getByLabelText("Artist scope"), { target: { value: "tagged" } });
    fireEvent.change(screen.getByLabelText("Local tag"), { target: { value: "chosen" } });
    fireEvent.change(screen.getByLabelText("Artist scope"), { target: { value: "stale" } });
    fireEvent.change(screen.getByLabelText("Not checked for days"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("Artist scope"), { target: { value: scope } });
    fireEvent.click(screen.getByRole("button", { name: "Run Workflow" }));
    await waitFor(() => expect(run).toHaveBeenCalledOnce());
    expect(run.mock.calls[0][0].definition.nodes[0].config).toEqual({
      scope: canonical, max_artists: 20,
      ...(scope === "tagged" ? { tag: "chosen" } : {}),
      ...(scope === "stale" ? { days: 7 } : {})
    });
    client.clear();
  });

  it.each([
    { tags: ["cat", "dog"] },
    { tag: "bird", tags: ["cat", "dog"] },
    { tag: "cat", tags: ["cat", "dog"] },
    { tag: "cat" },
    { tags: ["big cat", "red,blue"] },
    { tag: "", tags: [] }
  ])("round-trips the complete tag union %j", async (tagConfig) => {
    const config = { scope: "artists_with_tag", ...tagConfig, max_artists: 19,
      filters: [{ type: "last_checked_before_days", days: 7 }], artist_selection: "newest_checked_first",
      skip_unavailable_artists: false };
    const definition = savedDefinition(config);
    const save = mockSave(definition);
    const client = builder(definition);
    expect(inputValue("Local tag")).toBe(tagConfig.tag ?? "");
    expect(inputValue("Additional local tags (one per line)")).toBe(tagConfig.tags?.join("\n") ?? "");
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].definition).toEqual(definition.definition);
    client.clear();
  });

  it.each([
    ["Local tag", "bird", { tag: "bird", tags: ["cat", "dog"] }],
    ["Local tag", "", { tag: "", tags: ["cat", "dog"] }],
    ["Additional local tags (one per line)", "big cat\nred,blue", { tag: "cat", tags: ["big cat", "red,blue"] }],
    ["Additional local tags (one per line)", "", { tag: "cat", tags: [] }]
  ])("editing %s preserves the other tag field", async (label, value, editedTags) => {
    const config = { scope: "artists_with_tag", tag: "cat", tags: ["cat", "dog"], max_artists: 10 };
    const definition = savedDefinition(config);
    const save = mockSave(definition);
    const client = builder(definition);
    fireEvent.change(screen.getByLabelText(label as string), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].definition.nodes[0].config).toEqual({ ...config, ...editedTags as object });
    client.clear();
  });

  it.each([
    { scope: "single_artist", artist_id: "42" },
    { scope: "single_artist", artist_id: "42", artist_ids: ["ignored"], artwork_ids: ["ignored"] },
    { scope: "single_artist", artist_ids: ["42"] }
  ])("round-trips single_artist precedence and fallback %j", async (config) => {
    const definition = savedDefinition(config);
    const save = mockSave(definition);
    const client = builder(definition);
    expect(inputValue("Artist scope")).toBe("single");
    expect(inputValue("Artist ID")).toBe("42");
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].definition).toEqual(definition.definition);
    client.clear();
  });

  it.each(["77", ""])("edits a single artist to '%s' without activating fallback IDs", async (artistId) => {
    const config = { scope: "single_artist", artist_id: "42", artist_ids: ["ignored"], max_artists: 15 };
    const definition = savedDefinition(config);
    const save = mockSave(definition);
    const client = builder(definition);
    fireEvent.change(screen.getByLabelText("Artist ID"), { target: { value: artistId } });
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].definition.nodes[0].config).toEqual({
      ...config, artist_id: artistId, artist_ids: artistId ? ["ignored"] : []
    });
    client.clear();
  });

  it("converts a single artist to an explicit artist list only when the user switches scope", async () => {
    const definition = savedDefinition({ scope: "single_artist", artist_id: "42", artist_ids: ["ignored"],
      artwork_ids: ["ignored"], artist_source: "artwork_ids", tag: "ignored", days: 5,
      max_artists: 12, skip_unavailable_artists: false });
    const save = mockSave(definition);
    const client = builder(definition);
    fireEvent.change(screen.getByLabelText("Artist scope"), { target: { value: "selected" } });
    expect(inputValue("Artist IDs")).toBe("42");
    fireEvent.change(screen.getByLabelText("Artist IDs"), { target: { value: "42\n77" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].definition.nodes[0].config).toEqual({
      scope: "selected", artist_ids: ["42", "77"], max_artists: 12, skip_unavailable_artists: false
    });
    client.clear();
  });

  it("carries the edited single ID across scope changes and remembers explicit cleanup on switching back", async () => {
    const definition = savedDefinition({ scope: "single_artist", artist_id: "42", artist_ids: ["ignored"],
      artwork_ids: ["ignored"], tags: ["ignored"], max_artists: 12 });
    const save = mockSave(definition);
    const client = builder(definition);
    fireEvent.change(screen.getByLabelText("Artist ID"), { target: { value: "77" } });
    fireEvent.change(screen.getByLabelText("Artist scope"), { target: { value: "selected" } });
    expect(inputValue("Artist IDs")).toBe("77");
    fireEvent.change(screen.getByLabelText("Artist scope"), { target: { value: "single" } });
    expect(inputValue("Artist ID")).toBe("77");
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].definition.nodes[0].config).toEqual({ scope: "single_artist", artist_id: "77", max_artists: 12 });
    client.clear();
  });

  it.each(["selected", "artists"])("edits %s combined artist ID fields without resurrecting the scalar ID", async (scope) => {
    const config = { scope, artist_id: "42", artist_ids: ["77"], artist_source: "artist_ids", max_artists: 8,
      ...(scope === "artists" ? { artwork_ids: ["ignored"] } : {}) };
    const definition = savedDefinition(config);
    const save = mockSave(definition);
    const client = builder(definition);
    expect(inputValue("Artist IDs")).toBe("42\n77");
    fireEvent.change(screen.getByLabelText("Artist IDs"), { target: { value: "88\n99" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    const expected: Record<string, unknown> = { ...config, artist_ids: ["88", "99"] };
    delete expected.artist_id;
    expect(save.mock.calls[0][0].definition.nodes[0].config).toEqual(expected);
    client.clear();
  });

  it.each([
    { scope: "selected", artist_id: "42", artist_ids: ["77"] },
    { scope: "artists", artist_source: "artist_ids", artist_ids: ["42"], artwork_ids: ["ignored"] },
    { artist_ids: ["42"] },
    { scope: "artists_not_checked", days: 0, stale_days: 7 },
    { scope: "all_artists" },
    { scope: "all_artists", max_artists: null },
    { scope: "selected", artist_ids: ["42"], max_artists: 0 }
  ])("preserves valid optional parameters and backend defaults %j", async (config) => {
    const definition = savedDefinition(config);
    const save = mockSave(definition);
    const client = builder(definition);
    if ("stale_days" in config) expect(inputValue("Not checked for days")).toBe("7");
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].definition.nodes[0].config).toEqual({ scope: "selected", ...config });
    client.clear();
  });

  it.each([
    { scope: "single_artwork", artwork_id: "100" },
    { scope: "artworks", artwork_ids: ["100", "200"] },
    { scope: "artists", artist_source: "artwork_ids", artwork_ids: ["100"] },
    { scope: "selected", artist_ids: ["42"], artwork_ids: ["100"] },
    { scope: "selected", artwork_id: "100" },
    { scope: "future_scope", artist_ids: ["42"] },
    { scope: "single_artist", artist_ids: ["42", "77"] },
    { scope: "artists_with_tag", tags: ["cat\ndog"] },
    { scope: "artists_with_tag", tags: [123] }
  ])("shows and blocks unsupported target configurations %j", (config) => {
    const definition = savedDefinition(config);
    const save = mockSave(definition);
    const run = vi.spyOn(workflows, "createAdvancedWorkflowRun").mockResolvedValue({ id: "run" } as WorkflowRun);
    const client = builder(definition);
    expect(screen.getByRole("alert").textContent).toMatch(/preserved.*disabled/);
    expect(inputValue("Artist scope")).toBe("unsupported");
    expect((screen.getByRole("button", { name: "Save Workflow" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    fireEvent.click(screen.getByRole("tab", { name: "JSON" }));
    expect(JSON.parse(document.querySelector("pre")!.textContent!).definition).toEqual(definition.definition);
    expect(save).not.toHaveBeenCalled();
    expect(run).not.toHaveBeenCalled();
    client.clear();
  });

  it.each([0, 2])("blocks definitions with %s target nodes", (count) => {
    const definition = savedDefinition({ scope: "selected", artist_ids: ["42"] });
    definition.definition.nodes = Array.from({ length: count }, (_, index) => ({
      id: `target-${index}`, type: "artist_target", config: { artist_ids: [String(index)] }
    }));
    const save = mockSave(definition);
    const client = builder(definition);
    expect(screen.getByRole("alert").textContent).toContain("exactly one artist target");
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    expect(save).not.toHaveBeenCalled();
    client.clear();
  });

  it("preserves inactive fields on ordinary edits and removes them only after switching scope", async () => {
    const config = { scope: "artists_with_tag", tag: "cat", tags: ["dog"], artist_ids: ["ignored"],
      artwork_ids: ["ignored"], days: 7, stale_days: 9, max_artists: 15,
      filters: [{ type: "last_checked_before_days", days: 3 }], artist_selection: "random", skip_unavailable_artists: false };
    const definition = savedDefinition(config);
    const save = mockSave(definition);
    const client = builder(definition);
    fireEvent.change(screen.getByLabelText("Max artists per run"), { target: { value: "18" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save.mock.calls[0][0].definition.nodes[0].config).toEqual({ ...config, max_artists: 18 });
    fireEvent.change(screen.getByLabelText("Artist scope"), { target: { value: "all" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(save.mock.calls[1][0].definition.nodes[0].config).toEqual({
      scope: "all_artists", max_artists: 18, filters: config.filters, artist_selection: "random", skip_unavailable_artists: false
    });
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(3));
    expect(save.mock.calls[2][0].definition).toEqual(definition.definition);
    client.clear();
  });

  it("retains other nodes, retry pipelines, metadata and node identity during target edits", async () => {
    const definition = savedDefinition({ scope: "selected", artist_ids: ["42"], max_artists: 15 });
    const otherNodes = [
      { id: "sync-none", type: "sync_metadata", title: "Original sync", config: { mode: "none", custom: "retained" } },
      { id: "collect-original", type: "collect_artworks", config: { mode: "pending_files", max_artworks: null } },
      { id: "filters-original", type: "filter_artworks", config: { stop_above_limit: 100 } },
      { id: "actions-original", type: "execute_actions", config: { download: true, tag_variants: [{ tag: "cat", behavior: "skip" }] } },
      { id: "collect-retry", type: "collect_artworks", config: { mode: "failed_files" } },
      { id: "actions-retry", type: "execute_actions", config: { download: true, conflict_mode: "rename" } },
      { id: "other", type: "job_action", config: { actions: ["sync_artist"] } }
    ];
    definition.definition.nodes = [...definition.definition.nodes as object[], ...otherNodes];
    const save = mockSave(definition);
    const client = builder(definition);
    fireEvent.change(screen.getByLabelText("Artist IDs"), { target: { value: "77" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].definition).toEqual({ ...definition.definition, nodes: [
      { id: "legacy-target", type: "artist_target", title: "Original target", config: { scope: "selected", artist_ids: ["77"], max_artists: 15 } },
      ...otherNodes
    ] });
    client.clear();
  });

  it("updates an edited node field while retaining its other options and the original target", async () => {
    const definition = savedDefinition({ scope: "artists_with_tag", tags: ["cat", "dog"], max_artists: null });
    definition.definition.nodes = [...definition.definition.nodes as object[], {
      id: "original-sync", type: "sync_metadata", title: "Custom sync title", config: { mode: "incremental", retained: true }
    }];
    const save = mockSave(definition);
    const client = builder(definition);
    fireEvent.click(screen.getByRole("button", { name: /^3 Sync/ }));
    fireEvent.click(screen.getByRole("button", { name: "Full rescan" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    const originalNodes = definition.definition.nodes as Array<{ config: Record<string, unknown> }>;
    expect(save.mock.calls[0][0].definition.nodes).toEqual([
      originalNodes[0], { ...originalNodes[1], config: { mode: "full", retained: true } }
    ]);
    client.clear();
  });

  it("runs a new multi-tag target without reducing it to the scalar tag", async () => {
    const run = vi.spyOn(workflows, "createAdvancedWorkflowRun").mockResolvedValue({ id: "run" } as WorkflowRun);
    const client = builder();
    fireEvent.change(screen.getByLabelText("Artist scope"), { target: { value: "tagged" } });
    fireEvent.change(screen.getByLabelText("Local tag"), { target: { value: "bird" } });
    fireEvent.change(screen.getByLabelText("Additional local tags (one per line)"), { target: { value: "cat\ndog" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Workflow" }));
    await waitFor(() => expect(run).toHaveBeenCalledOnce());
    expect(run.mock.calls[0][0].definition.nodes[0].config).toEqual({
      scope: "artists_with_tag", tag: "bird", tags: ["cat", "dog"], max_artists: 20
    });
    client.clear();
  });

  it.each(["active", "paused"])("leaves an unchanged %s schedule and all triggers alone during target edits", async (status) => {
    const definition = savedDefinition({ scope: "single_artist", artist_id: "42" });
    definition.triggers = [1, 2].map((id) => ({ id, workflow_definition_id: definition.id, status,
      schedule: { type: "interval", every: 6, unit: "hours", run_after_startup: true },
      next_run_at: "2030-01-01T00:00:00Z", last_run_at: null, last_success_at: null, last_error_code: null,
      last_error_message: null, created_at: null, updated_at: null }));
    const save = mockSave(definition);
    const client = builder(definition);
    fireEvent.change(screen.getByLabelText("Artist ID"), { target: { value: "77" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].trigger).toBeNull();
    expect(save.mock.calls[0][0].definition.nodes[0].config).toEqual({ scope: "single_artist", artist_id: "77" });
    client.clear();
  });

  it("preserves schedule compatibility options and pause state when its interval is edited", async () => {
    const definition = savedDefinition({ scope: "selected", artist_ids: ["42"] });
    definition.triggers = [{ id: 1, workflow_definition_id: definition.id, status: "paused",
      schedule: { type: "interval", every: 6, unit: "hours", timezone: "Asia/Tokyo", run_after_startup: true },
      next_run_at: null, last_run_at: null, last_success_at: null, last_error_code: "old_error",
      last_error_message: "Old error", created_at: null, updated_at: null }];
    const save = mockSave(definition);
    const client = builder(definition);
    fireEvent.click(screen.getByRole("button", { name: /^1 Trigger/ }));
    fireEvent.change(screen.getByLabelText("Every"), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].trigger).toEqual({ trigger_id: 1, enabled: false, run_now: false,
      schedule: { ...definition.triggers[0].schedule, every: 8 } });
    client.clear();
  });
});
