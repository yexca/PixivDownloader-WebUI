import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import * as workflows from "@/api/workflows";
import * as jobs from "@/api/jobs";
import * as settings from "@/api/settings";
import type { WorkflowDefinition, WorkflowScheduleRule, WorkflowTrigger } from "@/api/workflows";
import { AdvancedWorkflowBuilder } from "@/components/workflows/AdvancedWorkflowBuilder";
import { ToastProvider } from "@/components/ToastProvider";
import { WorkflowsPage } from "@/pages/WorkflowsPage";

const schedules: WorkflowScheduleRule[] = [
  { type: "interval", every: 6, unit: "hours" },
  { type: "daily", time: "18:30", timezone: "Asia/Tokyo" },
  { type: "weekly", days_of_week: [2, 7], time: "18:30", timezone: "Asia/Tokyo" },
  { type: "monthly", day: "last", time: "18:30", timezone: "Asia/Tokyo" }
];
const compatibility = {
  run_after_startup: true,
  compat_scheduled_task: { run_after_startup: true, interval_days: 7 },
  compat_workflow_trigger: { retained: true }
};

function trigger(id: number, schedule: Record<string, unknown>, status = "paused"): WorkflowTrigger {
  return {
    id, workflow_definition_id: "saved", status, schedule,
    next_run_at: status === "active" ? "2030-01-01T00:00:00Z" : null,
    last_run_at: "2026-01-01T00:00:00Z", last_success_at: null,
    last_error_code: "old_error", last_error_message: "Old error", created_at: null, updated_at: null
  };
}

function definition(schedule: WorkflowScheduleRule = schedules[0], status = "paused"): WorkflowDefinition {
  return {
    id: "saved", name: "Saved workflow", created_at: null, updated_at: null,
    triggers: [
      trigger(1, { type: "daily", time: "03:00", timezone: "UTC", first_only: true }, "active"),
      trigger(2, { ...schedule, timezone: "Asia/Tokyo", ...compatibility }, status)
    ],
    definition: {
      name: "Saved workflow", metadata: { retained: true }, nodes: [
        { id: "original-target", type: "artist_target", title: "Tags", config: {
          scope: "artists_with_tag", tag: "bird", tags: ["cat", "dog"], max_artists: null,
          artist_selection: "random", skip_unavailable_artists: false
        } },
        { id: "original-sync", type: "sync_metadata", title: "Sync", config: { mode: "incremental", retained: true } },
        { id: "other", type: "job_action", config: { actions: ["sync_artist"] } }
      ]
    }
  };
}

function client() {
  return new QueryClient({ defaultOptions: {
    queries: { retry: false, gcTime: 0 }, mutations: { retry: false, gcTime: 0 }
  } });
}

function builder(saved: WorkflowDefinition | null, triggerId?: number | null) {
  const queryClient = client();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}><ToastProvider>{children}</ToastProvider></QueryClientProvider>
  );
  const element = (current: WorkflowDefinition | null, id?: number | null) => (
    <AdvancedWorkflowBuilder definition={current} triggerId={id} initialStage="trigger" />
  );
  const view = render(element(saved, triggerId), { wrapper });
  return { queryClient, select: (current: WorkflowDefinition | null, id?: number | null) => view.rerender(element(current, id)) };
}

function mockSave(saved: WorkflowDefinition) {
  return vi.spyOn(workflows, "saveWorkflowDefinition").mockResolvedValue({ definition: saved, trigger: null, run: null });
}

function change(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function value(label: string) {
  return (screen.getByLabelText(label) as HTMLInputElement | HTMLSelectElement).value;
}

beforeEach(() => {
  vi.spyOn(workflows, "createAdvancedWorkflowRun").mockRejectedValue(new Error("Unexpected workflow run"));
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Unexpected network request")));
});

describe("advanced workflow trigger selection", () => {
  it("reads, compares and merges the second interval trigger without using the first daily rule", async () => {
    const saved = definition();
    const original = structuredClone(saved);
    const save = mockSave(saved);
    const view = builder(saved, 2);
    expect(value("Schedule type")).toBe("interval");
    expect(value("Every")).toBe("6");
    expect(value("Unit")).toBe("hours");
    expect(screen.queryByLabelText("Time")).toBeNull();
    expect(screen.queryByLabelText("Time zone (IANA)")).toBeNull();
    expect(screen.getByText("Editing trigger #2 · paused")).toBeTruthy();
    change("Every", "8");
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0]).toEqual({
      definition_id: saved.id, definition: saved.definition,
      trigger: { trigger_id: 2, enabled: false, run_now: false, schedule: { ...saved.triggers[1].schedule, every: 8 } }
    });
    expect(saved).toEqual(original);
    view.queryClient.clear();
  });

  it.each([undefined, null])("consistently defaults to the first trigger when the ID is %s", async (id) => {
    const saved = definition();
    const save = mockSave(saved);
    const view = builder(saved, id);
    expect(value("Schedule type")).toBe("daily");
    expect(value("Time")).toBe("03:00");
    expect(value("Time zone (IANA)")).toBe("UTC");
    expect(screen.getByText("Editing trigger #1 · active")).toBeTruthy();
    change("Time", "04:00");
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].trigger).toEqual({ trigger_id: 1, enabled: true, run_now: false,
      schedule: { ...saved.triggers[0].schedule, time: "04:00" } });
    view.queryClient.clear();
  });

  it("uses the selected daily rule as the comparison baseline even when the edit matches the first trigger", async () => {
    const saved = definition(schedules[1]);
    const save = mockSave(saved);
    const view = builder(saved, 2);
    expect(value("Time")).toBe("18:30");
    change("Time", "03:00");
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].trigger).toEqual({ trigger_id: 2, enabled: false, run_now: false,
      schedule: { ...saved.triggers[1].schedule, time: "03:00" } });
    view.queryClient.clear();
  });

  it("refreshes both the draft and baseline on trigger switches and resets to the current trigger", async () => {
    const saved = definition();
    const save = mockSave(saved);
    const view = builder(saved, 1);
    change("Time", "04:00");
    view.select(saved, 2);
    expect(value("Schedule type")).toBe("interval");
    expect(value("Every")).toBe("6");
    change("Every", "8");
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(value("Every")).toBe("6");
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save.mock.calls[0][0].trigger).toBeNull();
    change("Every", "8");
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(save.mock.calls[1][0].trigger?.trigger_id).toBe(2);
    view.select(saved, 1);
    expect(value("Time")).toBe("03:00");
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(3));
    expect(save.mock.calls[2][0].trigger).toBeNull();
    view.queryClient.clear();
  });

  it.each([0, 999])("blocks an explicit missing trigger ID %s and can recover by selecting a valid one", (id) => {
    const saved = definition();
    const save = mockSave(saved);
    const view = builder(saved, id);
    expect(screen.getByRole("alert").textContent).toContain(`Trigger #${id} is no longer available`);
    expect(screen.queryByLabelText("Schedule type")).toBeNull();
    const button = screen.getByRole("button", { name: "Save Workflow" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    fireEvent.click(screen.getByText("Run now", { selector: "button" }));
    fireEvent.click(screen.getByRole("button", { name: "Run Workflow" }));
    expect(save).not.toHaveBeenCalled();
    expect(workflows.createAdvancedWorkflowRun).not.toHaveBeenCalled();
    view.select(saved, 2);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(value("Every")).toBe("6");
    expect((screen.getByRole("button", { name: "Save Schedule" }) as HTMLButtonElement).disabled).toBe(false);
    view.queryClient.clear();
  });

  it("blocks the selected trigger if it disappears from a refreshed definition", () => {
    const saved = definition();
    const save = mockSave(saved);
    const view = builder(saved, 2);
    change("Every", "8");
    view.select({ ...saved, triggers: [saved.triggers[0]] }, 2);
    expect(screen.getByRole("alert").textContent).toContain("Trigger #2 is no longer available");
    expect(screen.queryByLabelText("Time")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save Workflow" }));
    expect(save).not.toHaveBeenCalled();
    view.queryClient.clear();
  });

  it.each(schedules)("does not touch an unchanged $type schedule during target and node edits", async (schedule) => {
    const saved = definition(schedule, schedule.type === "interval" ? "paused" : "active");
    const original = structuredClone(saved);
    const save = mockSave(saved);
    const view = builder(saved, 2);
    fireEvent.click(screen.getByRole("button", { name: /^2 Target/ }));
    change("Max artists per run", "18");
    fireEvent.click(screen.getByRole("button", { name: /^3 Sync/ }));
    fireEvent.click(screen.getByRole("button", { name: "Full rescan" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    const originalNodes = saved.definition.nodes as Array<{ config: Record<string, unknown> }>;
    expect(save.mock.calls[0][0]).toEqual({ definition_id: saved.id, trigger: null,
      definition: { ...saved.definition, nodes: [
        { ...originalNodes[0], config: { ...originalNodes[0].config, max_artists: 18 } },
        { ...originalNodes[1], config: { ...originalNodes[1].config, mode: "full" } }, originalNodes[2]
      ] } });
    expect(saved).toEqual(original);
    view.queryClient.clear();
  });

  it.each(schedules.flatMap((from) => schedules.filter((to) => to.type !== from.type).map((to) => ({ from, to }))))(
    "switches $from.type to $to.type while retaining compatibility and clearing old rule fields",
    async ({ from, to }) => {
      const saved = definition(from);
      const save = mockSave(saved);
      const view = builder(saved, 2);
      change("Schedule type", to.type);
      if (to.type === "interval") {
        change("Every", String(to.every));
        change("Unit", to.unit);
      } else {
        expect(value("Time zone (IANA)")).toBe("Asia/Tokyo");
        change("Time", "04:00");
        if (to.type === "monthly") change("Day", "last");
      }
      fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
      await waitFor(() => expect(save).toHaveBeenCalledOnce());
      const expected = to.type === "interval" ? to : {
        ...to, time: "04:00", ...(to.type === "weekly" ? { days_of_week: [1, 3, 5] } : {})
      };
      expect(save.mock.calls[0][0]).toEqual({ definition_id: saved.id, definition: saved.definition,
        trigger: { trigger_id: 2, enabled: false, run_now: false, schedule: { ...compatibility, ...expected } } });
      view.queryClient.clear();
    }
  );

  it("supports a new schedule for a definition without triggers", async () => {
    const saved = { ...definition(), triggers: [] };
    const save = mockSave(saved);
    const view = builder(saved);
    fireEvent.click(screen.getByRole("button", { name: "Schedule" }));
    change("Schedule type", "daily");
    change("Time", "04:00");
    change("Time zone (IANA)", "Asia/Tokyo");
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].trigger).toEqual({ trigger_id: null, enabled: true, run_now: false,
      schedule: { type: "daily", time: "04:00", timezone: "Asia/Tokyo" } });
    view.queryClient.clear();
  });

  it("keeps Run + schedule tied to the selected paused trigger", async () => {
    const saved = definition();
    const save = mockSave(saved);
    const view = builder(saved, 2);
    fireEvent.click(screen.getByRole("button", { name: "Run + schedule" }));
    fireEvent.click(screen.getByRole("button", { name: "Run + Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].trigger).toEqual({ trigger_id: 2, enabled: false, run_now: true,
      schedule: saved.triggers[1].schedule });
    view.queryClient.clear();
  });

  it("opens and saves the second schedule through WorkflowsPage", async () => {
    const saved = definition();
    const save = mockSave(saved);
    vi.spyOn(workflows, "listWorkflowDefinitions").mockResolvedValue({ items: [saved], total: 1 });
    vi.spyOn(workflows, "listWorkflowRuns").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(jobs, "listJobs").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(settings, "getSettings").mockResolvedValue({ max_active_workflow_triggers: 1 } as settings.SettingsResponse);
    const queryClient = client();
    render(<QueryClientProvider client={queryClient}><ToastProvider>
      <MemoryRouter initialEntries={["/workflows?filter=scheduled"]}><WorkflowsPage /></MemoryRouter>
    </ToastProvider></QueryClientProvider>);
    const editButtons = await screen.findAllByRole("button", { name: "Edit schedule" });
    fireEvent.click(editButtons[1]);
    expect(value("Schedule type")).toBe("interval");
    change("Schedule type", "daily");
    change("Time", "04:00");
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save Schedule" }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0].trigger).toEqual({ trigger_id: 2, enabled: false, run_now: false,
      schedule: { ...compatibility, type: "daily", time: "04:00", timezone: "Asia/Tokyo" } });
    queryClient.clear();
  });
});
