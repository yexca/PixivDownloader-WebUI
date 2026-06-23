import { apiRequest } from "./client";

export type DownloadMode = "artist" | "artwork";

export type DownloadCreateRequest = {
  user_id: string | null;
  artwork_id: string | null;
  mode: DownloadMode;
  force_rescan: boolean;
  retry_failed: boolean;
};

export type DownloadCreateResponse = {
  job_id: string;
  status: string;
};

export function createDownloadJob(request: DownloadCreateRequest): Promise<DownloadCreateResponse> {
  return apiRequest<DownloadCreateResponse>("/downloads", {
    method: "POST",
    body: request
  });
}
