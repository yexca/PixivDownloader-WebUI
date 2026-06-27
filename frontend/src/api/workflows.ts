import { apiRequest } from "./client";
import type { ScheduledTaskConfig } from "./scheduledTasks";

export type WorkflowRunRequest = {
  config: ScheduledTaskConfig;
};

export type WorkflowRunResponse = {
  job_ids: string[];
  created: boolean;
};

export function runWorkflow(request: WorkflowRunRequest): Promise<WorkflowRunResponse> {
  return apiRequest<WorkflowRunResponse>("/workflows/run", {
    method: "POST",
    body: request
  });
}
