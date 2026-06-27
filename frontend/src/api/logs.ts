import { apiRequest } from "./client";
import type { JobEvent } from "./jobs";

export type LogListResponse = {
  items: JobEvent[];
  total: number;
};

export type ListLogsParams = {
  level?: string;
  limit?: number;
  offset?: number;
};

export function getRecentLogs(params: ListLogsParams = {}): Promise<LogListResponse> {
  const search = new URLSearchParams();
  if (params.level) {
    search.set("level", params.level);
  }
  if (params.limit) {
    search.set("limit", String(params.limit));
  }
  if (params.offset) {
    search.set("offset", String(params.offset));
  }
  const query = search.toString();
  return apiRequest<LogListResponse>(`/logs/recent${query ? `?${query}` : ""}`);
}
