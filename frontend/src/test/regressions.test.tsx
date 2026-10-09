import * as React from "react";
import { describe, it, expect, vi } from "vitest";
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { WorkflowRun } from "@/api/workflows";
import type { Job, JobListResponse, JobStreamMessage } from "@/api/jobs";
import * as settingsApi from "@/api/settings";
import { apiRequest } from "@/api/client";
import { SettingsPage } from "@/pages/SettingsPage";
import { ToastProvider } from "@/components/ToastProvider";
import { WorkflowRunDetail } from "@/components/workflows/WorkflowRunDetail";
import { useJobStream } from "@/hooks/useJobStream";

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}
function run(id = "run"): WorkflowRun {
  return { id, name: "Run", status: "running", total: 2, completed: 0, failed: 0,
    skipped: 0, concurrency: 1, source: "advanced", schedule_id: null, definition_id: null,
    failure_reason: "unknown", failure: null, created_at: null, finished_at: null,
    node_runs: ["First", "Second"].map((title, position) => ({ id: position + 1, workflow_run_id: id,
      node_id: title, node_type: "sync_metadata", title, position, status: "pending",
      input: {}, output: {}, job_ids: [], error_message: null, failure_reason: "unknown",
      failure: null, created_at: null, started_at: null, finished_at: null })) };
}
function job(id: string): Job {
  return { id, type: "download", status: "queued", artist_id: null, input_user_id: null,
    input_artwork_id: null, options: {}, workflow_run_id: null, workflow_node_run_id: null,
    workflow_source: null, total_files: 0, completed_files: 0, skipped_files: 0, failed_files: 0,
    cancel_requested: false, created_at: null, started_at: null, finished_at: null,
    error_message: null, failure: null, related_jobs: [] };
}
class Socket {
  static instances: Socket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) { Socket.instances.push(this); }
  close() { this.onclose?.(); }
  progress(id: string, status: JobStreamMessage["status"]) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ type: "job_progress",
      job_id: id, status, total_files: 2, completed_files: 1, skipped_files: 0, failed_files: 0,
      message: "Progress", created_at: null } satisfies JobStreamMessage) }));
  }
}

describe("state regressions", () => {
  it("shows the first settings error even before the form exists", async () => {
    vi.spyOn(settingsApi, "getSettings").mockRejectedValue(new Error("Settings unavailable"));
    const queryClient = client();
    render(<QueryClientProvider client={queryClient}><ToastProvider><SettingsPage /></ToastProvider></QueryClientProvider>);
    expect(await screen.findByText("Could not load settings")).toBeTruthy();
    expect(screen.getByText("Settings unavailable")).toBeTruthy();
    expect(screen.queryByText("Loading settings")).toBeNull();
    queryClient.clear();
  });
  it("keeps the selected node during polling and resets for another run", () => {
    const initial = run();
    const view = render(<WorkflowRunDetail run={initial} jobs={[]} loading={false} />);
    fireEvent.click(screen.getByRole("button", { name: /Second/ }));
    expect(screen.getByRole("heading", { name: "Second" })).toBeTruthy();
    view.rerender(<WorkflowRunDetail run={{ ...initial, node_runs: initial.node_runs.map(node => ({ ...node, status: "running" })) }} jobs={[]} loading={false} />);
    expect(screen.getByRole("heading", { name: "Second" })).toBeTruthy();
    view.rerender(<WorkflowRunDetail run={run("other")} jobs={[]} loading={false} />);
    expect(screen.getByRole("heading", { name: "First" })).toBeTruthy();
  });
  it("resets job streams and updates every matching list cache", () => {
    Socket.instances = [];
    vi.stubGlobal("WebSocket", Socket);
    const queryClient = client();
    const keys = [["jobs", "all", 20, 1], ["jobs", "running", 50, 2]];
    for (const key of keys) queryClient.setQueryData<JobListResponse>(key, { items: [job("one"), job("two")], total: 2 });
    const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    const hook = renderHook(({ id }) => useJobStream(id), { initialProps: { id: "one" }, wrapper });
    const old = Socket.instances[0];
    act(() => { old.onopen?.(); old.progress("one", "completed"); });
    expect(hook.result.current.connected).toBe(true);
    for (const key of keys) expect(queryClient.getQueryData<JobListResponse>(key)?.items[0].status).toBe("completed");
    hook.rerender({ id: "two" });
    expect(hook.result.current.connected).toBe(false);
    expect(hook.result.current.lastMessage).toBeNull();
    act(() => { old.progress("one", "failed"); old.onclose?.(); });
    expect(hook.result.current.lastMessage).toBeNull();
    act(() => { Socket.instances[1].onopen?.(); Socket.instances[1].progress("two", "running"); });
    expect(hook.result.current.lastMessage?.job_id).toBe("two");
    for (const key of keys) expect(queryClient.getQueryData<JobListResponse>(key)?.items[1].status).toBe("running");
    queryClient.clear();
  });
  it("surfaces specific request validation reasons", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: {
      code: "validation_error", message: "Request validation failed.", details: { errors: [{ msg: "max_active_run_jobs cannot be null" }] }
    } }), { status: 422 })));
    await expect(apiRequest("/settings", { method: "PUT", body: { max_active_run_jobs: null } }))
      .rejects.toThrow("max_active_run_jobs cannot be null");
  });
});
