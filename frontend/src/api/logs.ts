import { apiRequest } from "./client";
import type { JobEvent } from "./jobs";

export function getRecentLogs(limit = 100): Promise<JobEvent[]> {
  return apiRequest<JobEvent[]>(`/logs/recent?limit=${limit}`);
}
