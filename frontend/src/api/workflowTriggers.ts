import { apiRequest } from "./client";

export type WorkflowTriggerAction = "sync_artist" | "download_artist" | "retry_failed_artist";
export type WorkflowTriggerStatus = "active" | "inactive" | "paused" | "blocked" | "archived";
export type WorkflowTriggerTargetType = "artists" | "artworks" | "single_artist" | "single_artwork" | "all_artists" | "artists_with_tag" | "artists_not_checked";
export type WorkflowTriggerFilterType = "last_checked_before_days" | "has_failed_files";
export type WorkflowTriggerArtistSelection = "oldest_checked_first" | "newest_checked_first" | "random";
export type FailureReason = "auth" | "disk" | "network" | "cancelled" | "target" | "rule" | "unknown";
export type FailureDetail = {
  code: string;
  reason: FailureReason;
  retryable: boolean;
  message: string | null;
};

export type WorkflowTriggerConfig = {
  target: {
    type: WorkflowTriggerTargetType;
    artist_id?: string | null;
    artwork_id?: string | null;
    artist_ids?: string[];
    artwork_ids?: string[];
    artist_source?: "artist_ids" | "artwork_ids";
    tag?: string | null;
    tags?: string[];
    days?: number | null;
  };
  filters: Array<{
    type: WorkflowTriggerFilterType;
    days?: number | null;
  }>;
  actions: WorkflowTriggerAction[];
  download_options: Record<string, unknown>;
  max_artists_per_run: number;
  artist_selection: WorkflowTriggerArtistSelection;
  skip_unavailable_artists: boolean;
};

export type WorkflowTriggerRuntime = {
  id: number;
  name: string;
  action: WorkflowTriggerAction;
  status: WorkflowTriggerStatus;
  target_artist_id: string;
  interval_days: number;
  run_after_startup: boolean;
  last_run_at: string | null;
  last_success_at: string | null;
  next_run_at: string | null;
  last_job_id: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  failure_reason: FailureReason;
  failure: FailureDetail | null;
  config: WorkflowTriggerConfig;
  last_run_summary: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
};

export type WorkflowTriggerListResponse = {
  items: WorkflowTriggerRuntime[];
  total: number;
};

export type WorkflowTriggerCreateRequest = {
  name: string;
  action: WorkflowTriggerAction;
  target_artist_id: string | null;
  interval_days: number;
  enabled: boolean;
  run_after_startup: boolean;
  config?: WorkflowTriggerConfig;
};

export type WorkflowTriggerUpdateRequest = Partial<{
  name: string;
  action: WorkflowTriggerAction;
  status: WorkflowTriggerStatus;
  target_artist_id: string;
  interval_days: number;
  run_after_startup: boolean;
  config: WorkflowTriggerConfig;
}>;

export type WorkflowTriggerRunResponse = {
  trigger: WorkflowTriggerRuntime;
  job_id: string | null;
  job_ids: string[];
  workflow_run_id: string | null;
  created: boolean;
  skipped: boolean;
};

export function listWorkflowTriggers(): Promise<WorkflowTriggerListResponse> {
  return apiRequest<WorkflowTriggerListResponse>("/workflows/triggers");
}

export function createWorkflowTrigger(request: WorkflowTriggerCreateRequest): Promise<WorkflowTriggerRuntime> {
  return apiRequest<WorkflowTriggerRuntime>("/workflows/triggers", {
    method: "POST",
    body: request
  });
}

export function updateWorkflowTrigger(
  triggerId: number,
  request: WorkflowTriggerUpdateRequest
): Promise<WorkflowTriggerRuntime> {
  return apiRequest<WorkflowTriggerRuntime>(`/workflows/triggers/${triggerId}`, {
    method: "PUT",
    body: request
  });
}

export function runWorkflowTrigger(triggerId: number): Promise<WorkflowTriggerRunResponse> {
  return apiRequest<WorkflowTriggerRunResponse>(`/workflows/triggers/${triggerId}/run`, {
    method: "POST"
  });
}

export function deleteWorkflowTrigger(triggerId: number): Promise<void> {
  return apiRequest<void>(`/workflows/triggers/${triggerId}`, {
    method: "DELETE"
  });
}
