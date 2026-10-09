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

describe("advanced workflow target protocol", () => {
  it.each([
    ["all", "all", "all_artists"],
    ["all_artists", "all", "all_artists"],
    ["tagged", "tagged", "artists_with_tag"],
    ["artists_with_tag", "tagged", "artists_with_tag"],
    ["stale", "stale", "artists_not_checked"],
    ["artists_not_checked", "stale", "artists_not_checked"]
  ])("edits and saves %s definitions using the canonical protocol", async (stored, ui, canonical) => {
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
      scope: canonical, max_artists: 19,
      ...(ui === "tagged" ? { tag: "chosen" } : {}),
      ...(ui === "stale" ? { days: 7 } : {})
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
});
