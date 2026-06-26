import { apiRequest } from "./client";

export type ScheduledTaskAction = "sync_artist" | "download_artist" | "retry_failed_artist";
export type ScheduledTaskStatus = "active" | "paused" | "blocked";

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
  target_artist_id: string;
  interval_days: number;
  enabled: boolean;
  run_after_startup: boolean;
};

export type ScheduledTaskUpdateRequest = Partial<{
  name: string;
  action: ScheduledTaskAction;
  status: ScheduledTaskStatus;
  target_artist_id: string;
  interval_days: number;
  run_after_startup: boolean;
}>;

export type ScheduledTaskRunResponse = {
  task: ScheduledTask;
  job_id: string | null;
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
