import { apiRequest } from "./client";

export type ExistingFileBehavior = "skip" | "overwrite" | "save_duplicate";

export type SettingsResponse = {
  download_path: string;
  download_path_editable: boolean;
  runtime_mode: string;
  refresh_token_configured: boolean;
  refresh_token_preview: string;
  request_base_delay_seconds: number;
  request_random_delay_seconds: number;
  max_concurrent_downloads: number;
  max_active_scheduled_tasks: number;
  max_active_one_time_tasks: number;
  min_free_space_gb: number;
  existing_file_behavior: ExistingFileBehavior;
  library_stale_check_days: number;
  overwrite_existing_files: boolean;
  skip_existing_files: boolean;
};

export type SettingsUpdateRequest = {
  download_path?: string;
  refresh_token?: string | null;
  request_base_delay_seconds?: number;
  request_random_delay_seconds?: number;
  max_concurrent_downloads?: number;
  max_active_scheduled_tasks?: number;
  max_active_one_time_tasks?: number;
  min_free_space_gb?: number;
  existing_file_behavior?: ExistingFileBehavior;
  library_stale_check_days?: number;
  overwrite_existing_files?: boolean;
  skip_existing_files?: boolean;
};

export type AuthValidationResponse = {
  ok: boolean;
  message: string;
};

export type PixivConnectionTestResponse = {
  ok: boolean;
  message: string;
  user_id: string;
  user_name: string;
};

export type PixivAuthStartResponse = {
  flow_id: string;
  login_url: string;
  expires_at: string;
};

export type PixivBrowserAuthStartResponse = PixivAuthStartResponse & {
  novnc_url: string;
};

export type PixivBrowserAuthStatusResponse = {
  flow_id: string;
  status: "pending" | "callback_received" | "completed" | "failed";
  expires_at: string;
  error?: string | null;
};

export type PixivBrowserAuthServiceStatusResponse = {
  configured: boolean;
  running: boolean;
  novnc_url: string;
  start_command: string;
  stop_command: string;
  message: string;
};

export type PixivAuthCompleteRequest = {
  flow_id: string;
  code_or_callback_url: string;
};

export type PixivAuthCompleteResponse = SettingsResponse & {
  message: string;
};

export type PixivAuthRefreshResponse = SettingsResponse & {
  message: string;
};

export type LegacyDatabaseImportResponse = {
  imported_artists: number;
  skipped_rows: number;
  total_rows: number;
  hydration_job_id?: string | null;
  message: string;
};

export function getSettings(): Promise<SettingsResponse> {
  return apiRequest<SettingsResponse>("/settings");
}

export function updateSettings(settings: SettingsUpdateRequest): Promise<SettingsResponse> {
  return apiRequest<SettingsResponse>("/settings", {
    method: "PUT",
    body: settings
  });
}

export function validatePixivAuth(): Promise<AuthValidationResponse> {
  return apiRequest<AuthValidationResponse>("/settings/validate-auth", {
    method: "POST"
  });
}

export function testPixivConnection(): Promise<PixivConnectionTestResponse> {
  return apiRequest<PixivConnectionTestResponse>("/settings/test-connection", {
    method: "POST"
  });
}

export function startPixivAuth(): Promise<PixivAuthStartResponse> {
  return apiRequest<PixivAuthStartResponse>("/settings/pixiv-auth/start", {
    method: "POST"
  });
}

export function startPixivBrowserAuth(): Promise<PixivBrowserAuthStartResponse> {
  return apiRequest<PixivBrowserAuthStartResponse>("/settings/pixiv-auth/browser/start", {
    method: "POST"
  });
}

export function getPixivBrowserAuthStatus(flowId: string): Promise<PixivBrowserAuthStatusResponse> {
  return apiRequest<PixivBrowserAuthStatusResponse>(`/settings/pixiv-auth/browser/${flowId}`);
}

export function getPixivBrowserAuthServiceStatus(): Promise<PixivBrowserAuthServiceStatusResponse> {
  return apiRequest<PixivBrowserAuthServiceStatusResponse>("/settings/pixiv-auth/browser-service");
}

export function completePixivAuth(request: PixivAuthCompleteRequest): Promise<PixivAuthCompleteResponse> {
  return apiRequest<PixivAuthCompleteResponse>("/settings/pixiv-auth/complete", {
    method: "POST",
    body: request
  });
}

export function refreshPixivAuth(): Promise<PixivAuthRefreshResponse> {
  return apiRequest<PixivAuthRefreshResponse>("/settings/pixiv-auth/refresh", {
    method: "POST"
  });
}

export function importLegacyDatabase(file: File): Promise<LegacyDatabaseImportResponse> {
  const body = new FormData();
  body.set("file", file);
  return apiRequest<LegacyDatabaseImportResponse>("/imports/legacy-database", {
    method: "POST",
    body
  });
}
