import type { AdvancedWorkflowNode, WorkflowDefinition, WorkflowRun } from "@/api/workflows";

export function workflowNodes(definition: WorkflowDefinition): AdvancedWorkflowNode[] {
  const maybeNodes = (definition.definition as { nodes?: unknown }).nodes;
  if (!Array.isArray(maybeNodes)) {
    return [];
  }
  return maybeNodes.filter(isWorkflowNode);
}

export function recentDefinitionRuns(definition: WorkflowDefinition, runs: WorkflowRun[]): WorkflowRun[] {
  const triggerIds = new Set(definition.triggers.map((trigger) => trigger.id));
  return runs.filter((run) => {
    if (run.definition_id === definition.id) {
      return true;
    }
    if (run.schedule_id !== null && triggerIds.has(run.schedule_id)) {
      return true;
    }
    return runMatchesDefinition(definition, run);
  });
}

export function matchingDefinitionForRun(definitions: WorkflowDefinition[], run: WorkflowRun): WorkflowDefinition | null {
  return definitions.find((definition) => recentDefinitionRuns(definition, [run]).length > 0) ?? null;
}

export function definitionRunTitle(definition: WorkflowDefinition | null, run: WorkflowRun): string {
  const title = runTitle(run);
  if (!definition) {
    return title;
  }
  return title === "Workflow run" || title === "Target artists" ? definition.name : title;
}

export function runTitle(run: WorkflowRun): string {
  if (run.name?.trim()) {
    return run.name;
  }
  if (run.definition_id) {
    return "Workflow run";
  }
  if (run.node_runs.length && run.node_runs[0]?.title !== "Target artists") {
    return run.node_runs[0]?.title || "Workflow run";
  }
  return "Workflow run";
}

function runMatchesDefinition(definition: WorkflowDefinition, run: WorkflowRun): boolean {
  if (!run.node_runs.length || run.source !== "advanced_manual") {
    return false;
  }
  const nodes = workflowNodes(definition);
  if (nodes.length !== run.node_runs.length) {
    return false;
  }
  return nodes.every((node, index) => {
    const nodeRun = run.node_runs[index];
    const runConfig = nodeRun?.input?.config;
    return (
      nodeRun?.node_id === node.id &&
      nodeRun.node_type === node.type &&
      stableJson(runConfig) === stableJson(node.config ?? {})
    );
  });
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function isWorkflowNode(value: unknown): value is AdvancedWorkflowNode {
  if (!value || typeof value !== "object") {
    return false;
  }
  const node = value as Partial<AdvancedWorkflowNode>;
  return typeof node.id === "string" && typeof node.type === "string" && typeof node.config === "object";
}
