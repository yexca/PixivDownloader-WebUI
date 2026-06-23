import { apiRequest } from "./client";

export type HealthResponse = {
  status: string;
  version: string;
};

export function getHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health");
}
