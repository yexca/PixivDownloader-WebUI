import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { listWorkflowDefinitions, type WorkflowDefinition } from "@/api/workflows";
import * as workflows from "@/api/workflows";
import * as jobs from "@/api/jobs";
import * as settings from "@/api/settings";
import { AdvancedWorkflowBuilder } from "@/components/workflows/AdvancedWorkflowBuilder";
import { ToastProvider } from "@/components/ToastProvider";
import { WorkflowsPage } from "@/pages/WorkflowsPage";

async function loadWorkflow(rawDays = "[1.0]", effectiveDays: number[] | null = []) {
  const saved: WorkflowDefinition = {
    id: "saved", name: "Float weekdays", created_at: null, updated_at: null,
    definition: { name: "Float weekdays", nodes: [
      { id: "target", type: "artist_target", config: { scope: "all" } }
    ] },
    triggers: [1, 2].map((id) => ({
      id, workflow_definition_id: "saved", status: "paused",
      schedule: { type: "weekly", time: "04:00", timezone: "UTC", days_of_week: id === 1 ? [1] : "RAW_DAYS",
        compat_workflow_trigger: { retained: true } },
      effective_days_of_week: id === 1 ? [1] : effectiveDays,
      next_run_at: null, last_run_at: null, last_success_at: null,
      last_error_code: null, last_error_message: null, created_at: null, updated_at: null
    }))
  };
  // Exercise actual Response.json, API loading and request JSON.stringify, not just object mocks.
  const wire = JSON.stringify({ items: [saved], total: 1 }).replace('"RAW_DAYS"', rawDays);
  const fetch = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      return new Response(JSON.stringify({ definition: saved, trigger: null, run: null }), { status: 200 });
    }
    return new Response(wire, { status: 200 });
  });
  vi.stubGlobal("fetch", fetch);
  const loaded = (await listWorkflowDefinitions()).items[0];
  const queryClient = new QueryClient({ defaultOptions: {
    queries: { retry: false, gcTime: 0 }, mutations: { retry: false, gcTime: 0 }
  } });
  const element = (definition: WorkflowDefinition, triggerId: number) => (
    <QueryClientProvider client={queryClient}><ToastProvider>
      <AdvancedWorkflowBuilder definition={definition} triggerId={triggerId} initialStage="trigger" />
    </ToastProvider></QueryClientProvider>
  );
  const view = render(element(loaded, 2));
  return {
    loaded, queryClient,
    unmount: () => view.unmount(),
    select: (triggerId: number, definition = loaded) => view.rerender(element(definition, triggerId)),
    request: async () => {
      await waitFor(() => expect(fetch.mock.calls.some((call) => call[1]?.method === "POST")).toBe(true));
      return JSON.parse(String(fetch.mock.calls.find((call) => call[1]?.method === "POST")?.[1]?.body));
    },
    fetch
  };
}

function runAndSchedule() {
  fireEvent.click(screen.getByRole("button", { name: "Run + schedule" }));
  fireEvent.click(screen.getByRole("button", { name: "Run + Schedule" }));
}

describe("backend weekdays across JSON", () => {
  const cases = [
    { wire: "[1.0]", effective: [] },
    { wire: '[1.0,2,"03",true,2.5,7]', effective: [2, 3, 7] },
    { wire: '[1.0,"２"]', effective: [2] }
  ];

  it.each(cases)("displays backend weekdays and sends an empty patch for untouched $wire", async ({ wire, effective }) => {
    const view = await loadWorkflow(wire, effective);
    expect((view.loaded.triggers[1].schedule.days_of_week as unknown[])[0]).toBe(1);
    for (const [index, label] of ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].entries()) {
      expect(screen.getByRole("button", { name: label }).getAttribute("aria-pressed")).toBe(String(effective.includes(index + 1)));
    }
    if (!effective.length) expect(screen.getByText(/^Dynamic weekday:/)).toBeTruthy();
    runAndSchedule();
    expect((await view.request()).trigger).toEqual({ trigger_id: 2, enabled: false, run_now: true, schedule_patch: {} });
    view.queryClient.clear();
  });

  it.each(cases)("edits time without resending numeric weekdays for $wire", async ({ wire, effective }) => {
    const view = await loadWorkflow(wire, effective);
    fireEvent.change(screen.getByLabelText("Time"), { target: { value: "05:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    expect((await view.request()).trigger).toEqual({ trigger_id: 2, enabled: false, run_now: false,
      schedule_patch: { time: "05:00" } });
    view.queryClient.clear();
  });

  it.each([
    { wire: "[1.0]", effective: [], label: "Weekly (dynamic weekday) at 04:00" },
    { wire: '[1.0,2,"03",true,2.5,7]', effective: [2, 3, 7], label: "Weekly Tue, Wed, Sun at 04:00" },
    { wire: '[1.0,"２"]', effective: [2], label: "Weekly Tue at 04:00" },
    { wire: '["²"]', effective: null, label: "Weekly (weekday semantics unavailable) at 04:00" }
  ])("uses backend weekday semantics in both list and detail summaries for $wire", async ({ wire, effective, label }) => {
    const view = await loadWorkflow(wire, effective);
    view.unmount();
    vi.spyOn(workflows, "listWorkflowDefinitions").mockResolvedValue({ items: [{ ...view.loaded,
      triggers: [view.loaded.triggers[1], view.loaded.triggers[0]] }], total: 1 });
    vi.spyOn(workflows, "listWorkflowRuns").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(jobs, "listJobs").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(settings, "getSettings").mockResolvedValue({ max_active_workflow_triggers: 1 } as settings.SettingsResponse);
    render(<QueryClientProvider client={view.queryClient}><ToastProvider>
      <MemoryRouter initialEntries={["/workflows?filter=scheduled"]}><WorkflowsPage /></MemoryRouter>
    </ToastProvider></QueryClientProvider>);
    await waitFor(() => expect(screen.getAllByText(label)).toHaveLength(2));
    view.queryClient.clear();
  });

  it("replaces weekdays only when the user selects a fixed day", async () => {
    const view = await loadWorkflow();
    fireEvent.click(screen.getByRole("button", { name: "Mon" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    expect((await view.request()).trigger.schedule_patch).toEqual({ days_of_week: [1] });
    view.queryClient.clear();
  });

  it("preserves the rule during target edits", async () => {
    const view = await loadWorkflow();
    fireEvent.click(screen.getByRole("button", { name: /^2 Target/ }));
    fireEvent.change(screen.getByLabelText("Max artists per run"), { target: { value: "18" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    expect((await view.request()).trigger).toBeNull();
    view.queryClient.clear();
  });

  it("restores the authoritative baseline on Reset and trigger switches", async () => {
    const view = await loadWorkflow();
    fireEvent.click(screen.getByRole("button", { name: "Mon" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.getByRole("button", { name: "Mon" }).getAttribute("aria-pressed")).toBe("false");
    view.select(1);
    expect(screen.getByRole("button", { name: "Mon" }).getAttribute("aria-pressed")).toBe("true");
    view.select(2);
    expect(screen.getByText(/^Dynamic weekday:/)).toBeTruthy();
    runAndSchedule();
    expect((await view.request()).trigger.schedule_patch).toEqual({});
    view.queryClient.clear();
  });

  it("sends a complete applicable rule on an explicit type switch", async () => {
    const view = await loadWorkflow();
    fireEvent.change(screen.getByLabelText("Schedule type"), { target: { value: "daily" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
    expect((await view.request()).trigger.schedule_patch).toEqual({ type: "daily", time: "04:00", timezone: "UTC" });
    view.queryClient.clear();
  });

  it.each(["weekly", "interval"])("blocks older backend responses for %s instead of risking ignored patches", async (type) => {
    const view = await loadWorkflow();
    const old = structuredClone(view.loaded);
    old.triggers[1].schedule.type = type;
    delete old.triggers[1].effective_days_of_week;
    view.select(2, old);
    expect(screen.getByRole("alert").textContent).toContain("Backend schedule editing support is unavailable");
    expect((screen.getByRole("button", { name: "Save Schedule" }) as HTMLButtonElement).disabled).toBe(true);
    runAndSchedule();
    expect(view.fetch.mock.calls.filter((call) => call[1]?.method === "POST")).toHaveLength(0);
    view.queryClient.clear();
  });

  it("blocks a rule whose weekdays the backend could not interpret", async () => {
    const view = await loadWorkflow('["²"]', null);
    expect(screen.getByRole("alert").textContent).toContain("backend could not determine the stored weekday semantics");
    runAndSchedule();
    expect(view.fetch.mock.calls.filter((call) => call[1]?.method === "POST")).toHaveLength(0);
    view.queryClient.clear();
  });
});
