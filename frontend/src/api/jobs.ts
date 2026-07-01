import { apiRequest } from "./client";
import type { FailureDetail } from "./scheduledTasks";

export type JobStatus = "inactive" | "queued" | "running" | "completed" | "failed" | "cancelled";

export type RelatedJob = {
  id: string;
  status: JobStatus;
  action: string;
  created_at: string | null;
};

export type Job = {
  id: string;
  type: string;
  status: JobStatus;
  artist_id: string | null;
  input_user_id: string | null;
  input_artwork_id: string | null;
  options: Record<string, unknown>;
  workflow_run_id: string | null;
  workflow_item_id: number | null;
  workflow_node_run_id: number | null;
  workflow_source: string | null;
  total_files: number;
  completed_files: number;
  skipped_files: number;
  failed_files: number;
  cancel_requested: boolean;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  failure: FailureDetail | null;
  related_jobs: RelatedJob[];
};

export type JobEvent = {
  id: number | null;
  job_id: string;
  level: "debug" | "info" | "warning" | "error" | string;
  message: string;
  payload: Record<string, unknown> | null;
  created_at: string | null;
};

export type JobDetail = Job & {
  events: JobEvent[];
};

export type JobListResponse = {
  items: Job[];
  total: number;
};

export type JobCancelResponse = {
  job_id: string;
  status: JobStatus;
  cancel_requested: boolean;
};

export type JobActionResponse = {
  job_id: string;
  status: JobStatus;
  source_job_id: string;
  action: string;
};

export type JobBulkCancelResponse = {
  cancelled: JobCancelResponse[];
  errors: Array<{ job_id: string; message: string }>;
};

export type JobQueueState = {
  paused: boolean;
};

export type JobStreamMessage = {
  type: "job_progress" | "job_event" | "job_completed" | "job_failed" | "job_cancelled" | string;
  job_id: string;
  status: JobStatus;
  total_files: number;
  completed_files: number;
  skipped_files: number;
  failed_files: number;
  message: string;
  created_at: string | null;
};

export type ListJobsParams = {
  status?: JobStatus | "";
  limit?: number;
  offset?: number;
};

export function listJobs(params: ListJobsParams = {}): Promise<JobListResponse> {
  const search = new URLSearchParams();
  if (params.status) {
    search.set("status", params.status);
  }
  if (params.limit) {
    search.set("limit", String(params.limit));
  }
  if (params.offset) {
    search.set("offset", String(params.offset));
  }
  const query = search.toString();
  return apiRequest<JobListResponse>(`/jobs${query ? `?${query}` : ""}`);
}

export function getJob(jobId: string): Promise<JobDetail> {
  return apiRequest<JobDetail>(`/jobs/${jobId}`);
}

export function cancelJob(jobId: string): Promise<JobCancelResponse> {
  return apiRequest<JobCancelResponse>(`/jobs/${jobId}/cancel`, {
    method: "POST"
  });
}

export function retryJob(jobId: string): Promise<JobActionResponse> {
  return apiRequest<JobActionResponse>(`/jobs/${jobId}/retry`, {
    method: "POST"
  });
}

export function rerunJob(jobId: string): Promise<JobActionResponse> {
  return apiRequest<JobActionResponse>(`/jobs/${jobId}/rerun`, {
    method: "POST"
  });
}

export function bulkCancelJobs(jobIds: string[]): Promise<JobBulkCancelResponse> {
  return apiRequest<JobBulkCancelResponse>("/jobs/bulk-cancel", {
    method: "POST",
    body: { job_ids: jobIds }
  });
}

export function getJobQueueState(): Promise<JobQueueState> {
  return apiRequest<JobQueueState>("/jobs/queue");
}

export function pauseJobQueue(): Promise<JobQueueState> {
  return apiRequest<JobQueueState>("/jobs/queue/pause", {
    method: "POST"
  });
}

export function resumeJobQueue(): Promise<JobQueueState> {
  return apiRequest<JobQueueState>("/jobs/queue/resume", {
    method: "POST"
  });
}

export function listJobEvents(jobId: string): Promise<JobEvent[]> {
  return apiRequest<JobEvent[]>(`/jobs/${jobId}/events`);
}
