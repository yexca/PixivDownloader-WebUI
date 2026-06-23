import { apiRequest } from "./client";
import type { DownloadCreateResponse } from "./downloads";

export type ArtistSummary = {
  id: string;
  name: string;
  profile_url: string;
  avatar_url: string | null;
  artwork_count: number;
  downloaded_file_count: number;
  failed_file_count: number;
  last_checked_at: string | null;
};

export type ArtistDetail = ArtistSummary & {
  account: string | null;
  comment: string | null;
  legacy_last_download_id: string | null;
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

export type ListArtistsParams = {
  q?: string;
  sort?: string;
  limit?: number;
  offset?: number;
};

export function listArtists(params: ListArtistsParams = {}): Promise<ArtistListResponse> {
  const search = new URLSearchParams();
  if (params.q) {
    search.set("q", params.q);
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
