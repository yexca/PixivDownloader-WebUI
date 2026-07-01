import { apiRequest } from "./client";

export type ScheduledTaskAction = "sync_artist" | "download_artist" | "retry_failed_artist";
export type ScheduledTaskStatus = "active" | "inactive" | "paused" | "blocked" | "archived";
export type ScheduledTaskTargetType = "artists" | "artworks" | "single_artist" | "single_artwork" | "all_artists" | "artists_with_tag" | "artists_not_checked";
export type ScheduledTaskFilterType = "last_checked_before_days" | "has_failed_files";
export type ScheduledTaskArtistSelection = "oldest_checked_first" | "newest_checked_first" | "random";
export type FailureReason = "auth" | "disk" | "network" | "cancelled" | "target" | "rule" | "unknown";
export type FailureDetail = {
  code: string;
  reason: FailureReason;
  retryable: boolean;
  message: string | null;
};

export type ScheduledTaskConfig = {
  target: {
    type: ScheduledTaskTargetType;
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
    type: ScheduledTaskFilterType;
    days?: number | null;
  }>;
  actions: ScheduledTaskAction[];
  download_options: Record<string, unknown>;
  max_artists_per_run: number;
  artist_selection: ScheduledTaskArtistSelection;
  skip_unavailable_artists: boolean;
};

export type ScheduledTask = {
  id: number;
  name: string;
  action: ScheduledTaskAction;
  status: ScheduledTaskStatus;
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
  config: ScheduledTaskConfig;
  last_run_summary: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ScheduledTaskListResponse = {
  items: ScheduledTask[];
  total: number;
};

export type ScheduledTaskCreateRequest = {
  name: string;
  action: ScheduledTaskAction;
  target_artist_id: string | null;
  interval_days: number;
  enabled: boolean;
  run_after_startup: boolean;
  config?: ScheduledTaskConfig;
};

export type ScheduledTaskUpdateRequest = Partial<{
  name: string;
  action: ScheduledTaskAction;
  status: ScheduledTaskStatus;
  target_artist_id: string;
  interval_days: number;
  run_after_startup: boolean;
  config: ScheduledTaskConfig;
}>;

export type ScheduledTaskRunResponse = {
  task: ScheduledTask;
  job_id: string | null;
  job_ids: string[];
  workflow_run_id: string | null;
  created: boolean;
  skipped: boolean;
};

export function listScheduledTasks(): Promise<ScheduledTaskListResponse> {
  return apiRequest<ScheduledTaskListResponse>("/scheduled-tasks");
}

export function createScheduledTask(request: ScheduledTaskCreateRequest): Promise<ScheduledTask> {
  return apiRequest<ScheduledTask>("/scheduled-tasks", {
    method: "POST",
    body: request
  });
}

export function updateScheduledTask(
  taskId: number,
  request: ScheduledTaskUpdateRequest
): Promise<ScheduledTask> {
  return apiRequest<ScheduledTask>(`/scheduled-tasks/${taskId}`, {
    method: "PUT",
    body: request
  });
}

export function runScheduledTask(taskId: number): Promise<ScheduledTaskRunResponse> {
  return apiRequest<ScheduledTaskRunResponse>(`/scheduled-tasks/${taskId}/run`, {
    method: "POST"
  });
}

export function deleteScheduledTask(taskId: number): Promise<void> {
  return apiRequest<void>(`/scheduled-tasks/${taskId}`, {
    method: "DELETE"
  });
}
