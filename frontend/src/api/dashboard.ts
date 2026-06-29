import { apiRequest } from "./client";

export type DashboardSummary = {
  library: {
    artists: number;
    artworks: number;
    downloaded_files: number;
    pending_files: number;
    failed_files: number;
    attention_artists: number;
    artists_with_updates: number;
    artists_with_failed_files: number;
    unavailable_artists: number;
  };
  workflows: {
    running_runs: number;
    failed_runs: number;
    completed_runs: number;
    active_schedules: number;
    blocked_schedules: number;
    inactive_schedules: number;
    waiting_jobs: number;
  };
  jobs: {
    inactive: number;
    queued: number;
    running: number;
    completed: number;
    failed: number;
    cancelled: number;
  };
  queue_paused: boolean;
};

export function getDashboardSummary(): Promise<DashboardSummary> {
  return apiRequest<DashboardSummary>("/dashboard");
}
