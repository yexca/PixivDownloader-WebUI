import { apiRequest } from "./client";
import type { DownloadCreateResponse } from "./downloads";

export type ArtistSummary = {
  id: string;
  name: string;
  profile_url: string;
  avatar_url: string | null;
  avatar_cached: boolean;
  artwork_count: number;
  downloaded_file_count: number;
  remote_file_count: number;
  pending_file_count: number;
  failed_file_count: number;
  latest_downloaded_artwork_id: string | null;
  last_checked_at: string | null;
  account_status: "unknown" | "available" | "unavailable";
  account_status_checked_at: string | null;
  account_status_reason: string | null;
  remote_latest_artwork_id: string | null;
  remote_latest_checked_at: string | null;
  has_remote_update: boolean;
  is_check_stale: boolean;
  check_stale_days: number;
  local_tags: LocalTag[];
};

export type ArtistDetail = ArtistSummary & {
  account: string | null;
  comment: string | null;
  name_history: ArtistNameHistory[];
};

export type ArtistNameHistory = {
  id: number;
  name: string;
  source: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
};

export type ArtistListResponse = {
  items: ArtistSummary[];
  total: number;
};

export type ArtworkSummary = {
  id: string;
  artist_id: string;
  title: string;
  type: string | null;
  page_count: number;
  pixiv_created_at: string | null;
  total_files: number;
  downloaded_files: number;
  skipped_files: number;
  failed_files: number;
};

export type ArtworkListResponse = {
  items: ArtworkSummary[];
  total: number;
};

export type ArtworkFile = {
  id: number | null;
  artwork_id: string;
  page_index: number;
  original_url: string;
  local_path: string | null;
  file_name: string;
  size_bytes: number | null;
  status: string;
  downloaded_at: string | null;
  error_message: string | null;
};

export type ArtworkFileListResponse = {
  items: ArtworkFile[];
  total: number;
};

export type LocalTag = {
  id: number;
  name: string;
};

export type LocalTagListResponse = {
  items: LocalTag[];
  total: number;
};

export type ListArtistsParams = {
  q?: string;
  local_tag?: string;
  file_state?: string;
  tag_state?: string;
  account_status?: string;
  update_state?: string;
  sort?: string;
  limit?: number;
  offset?: number;
};

export function listArtists(params: ListArtistsParams = {}): Promise<ArtistListResponse> {
  const search = new URLSearchParams();
  if (params.q) {
    search.set("q", params.q);
  }
  if (params.local_tag) {
    search.set("local_tag", params.local_tag);
  }
  if (params.file_state) {
    search.set("file_state", params.file_state);
  }
  if (params.tag_state) {
    search.set("tag_state", params.tag_state);
  }
  if (params.account_status) {
    search.set("account_status", params.account_status);
  }
  if (params.update_state) {
    search.set("update_state", params.update_state);
  }
  if (params.sort) {
    search.set("sort", params.sort);
  }
  if (params.limit) {
    search.set("limit", String(params.limit));
  }
  if (params.offset) {
    search.set("offset", String(params.offset));
  }
  const query = search.toString();
  return apiRequest<ArtistListResponse>(`/artists${query ? `?${query}` : ""}`);
}

export function getArtist(artistId: string): Promise<ArtistDetail> {
  return apiRequest<ArtistDetail>(`/artists/${artistId}`);
}

export function createArtist(userId: string): Promise<DownloadCreateResponse> {
  return apiRequest<DownloadCreateResponse>("/artists", {
    method: "POST",
    body: { user_id: userId }
  });
}

export function syncArtist(artistId: string): Promise<DownloadCreateResponse> {
  return apiRequest<DownloadCreateResponse>(`/artists/${artistId}/sync`, {
    method: "POST"
  });
}

export function retryFailedArtist(artistId: string): Promise<DownloadCreateResponse> {
  return apiRequest<DownloadCreateResponse>(`/artists/${artistId}/retry-failed`, {
    method: "POST"
  });
}

export function deleteArtist(artistId: string): Promise<void> {
  return apiRequest<void>(`/artists/${artistId}`, {
    method: "DELETE"
  });
}

export function listLocalTags(): Promise<LocalTagListResponse> {
  return apiRequest<LocalTagListResponse>("/artists/-/local-tags");
}

export function setArtistLocalTags(
  artistId: string,
  tags: string[]
): Promise<LocalTagListResponse> {
  return apiRequest<LocalTagListResponse>(`/artists/${artistId}/local-tags`, {
    method: "PUT",
    body: { tags }
  });
}

export function listArtistArtworks(
  artistId: string,
  limit = 50,
  offset = 0
): Promise<ArtworkListResponse> {
  return apiRequest<ArtworkListResponse>(
    `/artists/${artistId}/artworks?limit=${limit}&offset=${offset}`
  );
}

export function listArtworkFiles(artworkId: string): Promise<ArtworkFileListResponse> {
  return apiRequest<ArtworkFileListResponse>(`/artworks/${artworkId}/files`);
}

export function retryArtworkFile(fileId: number): Promise<DownloadCreateResponse> {
  return apiRequest<DownloadCreateResponse>(`/artwork-files/${fileId}/retry`, {
    method: "POST"
  });
}
