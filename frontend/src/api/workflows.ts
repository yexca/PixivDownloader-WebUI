import { apiRequest } from "./client";
import type { FailureDetail, FailureReason } from "./scheduledTasks";

export type WorkflowBatchRunItem = {
  id: number | null;
  run_id: string;
  draft_id: string;
  title: string;
  status: "pending" | "completed" | "failed" | "skipped" | "running";
  job_ids: string[];
  error_message: string | null;
  failure_reason: FailureReason;
  failure: FailureDetail | null;
  config: Record<string, unknown>;
  request: Record<string, unknown>;
  created_at: string | null;
  finished_at: string | null;
};

export type WorkflowNodeRun = {
  id: number | null;
  workflow_run_id: string;
  node_id: string;
  node_type: string;
  title: string;
  position: number;
  status: "pending" | "completed" | "failed" | "skipped" | "running";
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  job_ids: string[];
  error_message: string | null;
  failure_reason: FailureReason;
  failure: FailureDetail | null;
  created_at: string | null;
  started_at: string | null;
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
  failure_reason: FailureReason;
  failure: FailureDetail | null;
  created_at: string | null;
  finished_at: string | null;
  items: WorkflowBatchRunItem[];
  node_runs: WorkflowNodeRun[];
};

export type WorkflowBatchRunListResponse = {
  items: WorkflowBatchRun[];
  total: number;
};

export type AdvancedWorkflowNode = {
  id: string;
  type:
    | "artist_target"
    | "sync_metadata"
    | "collect_artworks"
    | "filter_artworks"
    | "execute_actions";
  title?: string;
  config: Record<string, unknown>;
};

export type AdvancedWorkflowRunRequest = {
  definition: {
    name?: string;
    nodes: AdvancedWorkflowNode[];
  };
};

export type WorkflowScheduleRule =
  | { type: "interval"; every: number; unit: "minutes" | "hours" | "days" }
  | { type: "daily"; time: string }
  | { type: "weekly"; days_of_week: number[]; time: string }
  | { type: "monthly"; day: number | "last"; time: string };

export type WorkflowTrigger = {
  id: number;
  workflow_definition_id: string;
  status: string;
  schedule: Record<string, unknown>;
  next_run_at: string | null;
  last_run_at: string | null;
  last_success_at: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type WorkflowDefinition = {
  id: string;
  name: string;
  definition: Record<string, unknown>;
  triggers: WorkflowTrigger[];
  created_at: string | null;
  updated_at: string | null;
};

export type WorkflowDefinitionSaveRequest = {
  definition_id?: string | null;
  definition: AdvancedWorkflowRunRequest["definition"];
  trigger?: {
    enabled: boolean;
    schedule: WorkflowScheduleRule;
    run_now: boolean;
  } | null;
};

export type WorkflowDefinitionSaveResponse = {
  definition: WorkflowDefinition;
  trigger: WorkflowTrigger | null;
  run: WorkflowBatchRun | null;
};

export type WorkflowDefinitionListResponse = {
  items: WorkflowDefinition[];
  total: number;
};

export function createAdvancedWorkflowRun(request: AdvancedWorkflowRunRequest): Promise<WorkflowBatchRun> {
  return apiRequest<WorkflowBatchRun>("/workflows/advanced/runs", {
    method: "POST",
    body: request
  });
}

export function saveWorkflowDefinition(request: WorkflowDefinitionSaveRequest): Promise<WorkflowDefinitionSaveResponse> {
  return apiRequest<WorkflowDefinitionSaveResponse>("/workflows/definitions", {
    method: "POST",
    body: request
  });
}

export function runWorkflowDefinition(definitionId: string): Promise<WorkflowBatchRun> {
  return apiRequest<WorkflowBatchRun>(`/workflows/definitions/${definitionId}/run`, {
    method: "POST"
  });
}

export function listWorkflowDefinitions(): Promise<WorkflowDefinitionListResponse> {
  return apiRequest<WorkflowDefinitionListResponse>("/workflows/definitions");
}

export function listWorkflowRuns(limit = 5): Promise<WorkflowBatchRunListResponse> {
  return apiRequest<WorkflowBatchRunListResponse>(`/workflows/runs?limit=${limit}`);
}
