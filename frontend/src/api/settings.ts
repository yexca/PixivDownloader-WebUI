import { apiRequest } from "./client";

export type SettingsResponse = {
  download_path: string;
  refresh_token_configured: boolean;
  refresh_token_preview: string;
  request_base_delay_seconds: number;
  request_random_delay_seconds: number;
  max_concurrent_downloads: number;
  overwrite_existing_files: boolean;
  skip_existing_files: boolean;
};

export type SettingsUpdateRequest = {
  download_path: string;
  refresh_token?: string | null;
  request_base_delay_seconds: number;
  request_random_delay_seconds: number;
  max_concurrent_downloads: number;
  overwrite_existing_files: boolean;
  skip_existing_files: boolean;
};

export type AuthValidationResponse = {
  ok: boolean;
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
