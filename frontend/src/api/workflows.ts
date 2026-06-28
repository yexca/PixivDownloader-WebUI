import { apiRequest } from "./client";
import type { ScheduledTaskConfig } from "./scheduledTasks";

export type WorkflowRunRequest = {
  config: ScheduledTaskConfig;
};

export type WorkflowRunResponse = {
  job_ids: string[];
  created: boolean;
};

export type WorkflowBatchRunItem = {
  id: number | null;
  run_id: string;
  draft_id: string;
  title: string;
  status: "pending" | "completed" | "failed" | "skipped" | "running";
  job_ids: string[];
  error_message: string | null;
  config: Record<string, unknown>;
  request: Record<string, unknown>;
  created_at: string | null;
  finished_at: string | null;
};

export type WorkflowBatchRun = {
  id: string;
  status: "running" | "completed" | "failed" | "partial" | "skipped";
  total: number;
  completed: number;
  failed: number;
  skipped: number;
  concurrency: number;
  source: string;
  schedule_id: number | null;
  created_at: string | null;
  finished_at: string | null;
  items: WorkflowBatchRunItem[];
};

export type WorkflowBatchRunListResponse = {
  items: WorkflowBatchRun[];
  total: number;
};

export type WorkflowBatchRunRequest = {
  concurrency: number;
  items: Array<{
    draft_id: string;
    title: string;
    config: ScheduledTaskConfig;
    skip_if_last_run_failed?: boolean;
    schedule?: boolean;
    name?: string;
    interval_days?: number;
    enabled?: boolean;
    run_after_startup?: boolean;
  }>;
};

export function runWorkflow(request: WorkflowRunRequest): Promise<WorkflowRunResponse> {
  return apiRequest<WorkflowRunResponse>("/workflows/run", {
    method: "POST",
    body: request
  });
}

export function createWorkflowRun(request: WorkflowBatchRunRequest): Promise<WorkflowBatchRun> {
  return apiRequest<WorkflowBatchRun>("/workflows/runs", {
    method: "POST",
    body: request
  });
}

export function listWorkflowRuns(limit = 5): Promise<WorkflowBatchRunListResponse> {
  return apiRequest<WorkflowBatchRunListResponse>(`/workflows/runs?limit=${limit}`);
}
