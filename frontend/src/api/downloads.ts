import { apiRequest } from "./client";

export type DownloadMode = "artist" | "artwork";

export type DownloadCreateRequest = {
  user_id: string | null;
  artwork_id: string | null;
  mode: DownloadMode;
  force_rescan: boolean;
  retry_failed: boolean;
  full_download?: boolean;
  max_artworks?: number | null;
  min_artwork_id?: string | null;
  max_artwork_id?: string | null;
  naming_rule?: string | null;
  only_new_artworks?: boolean;
  stop_if_artwork_count_above?: number | null;
  naming_tag_variants?: Array<Record<string, string>>;
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
