from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.domain.types import FailureReason
from backend.repositories.workflow_definition_repository import (
    WorkflowDefinition,
    WorkflowDefinitionWithTriggers,
    WorkflowTrigger,
)
from backend.repositories.workflow_run_repository import (
    WorkflowNodeRun,
    WorkflowRun,
)
from backend.schemas.failure_reasons import FailureDetail, classify_failure_reason, failure_detail

AdvancedWorkflowNodeType = Literal[
    "artist_target",
    "sync_metadata",
    "collect_artworks",
    "filter_artworks",
    "execute_actions",
    "job_action",
    "legacy_import_hydration",
]


class AdvancedWorkflowNodeRequest(BaseModel):
    id: str
    type: AdvancedWorkflowNodeType
    title: str = ""
    config: dict[str, object] = Field(default_factory=dict)


class AdvancedWorkflowDefinitionRequest(BaseModel):
    name: str = ""
    nodes: list[AdvancedWorkflowNodeRequest] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class AdvancedWorkflowRunRequest(BaseModel):
    definition: AdvancedWorkflowDefinitionRequest


class WorkflowTriggerRequest(BaseModel):
    enabled: bool = True
    schedule: dict[str, object] = Field(default_factory=dict)
    run_now: bool = False


class WorkflowDefinitionSaveRequest(BaseModel):
    definition_id: str | None = None
    definition: AdvancedWorkflowDefinitionRequest
    trigger: WorkflowTriggerRequest | None = None


class WorkflowTriggerResponse(BaseModel):
    id: int
    workflow_definition_id: str
    status: str
    schedule: dict[str, object]
    next_run_at: str | None
    last_run_at: str | None
    last_success_at: str | None
    last_error_code: str | None
    last_error_message: str | None
    created_at: str | None
    updated_at: str | None


class WorkflowDefinitionResponse(BaseModel):
    id: str
    name: str
    definition: dict[str, object]
    triggers: list[WorkflowTriggerResponse] = Field(default_factory=list)
    created_at: str | None
    updated_at: str | None


class WorkflowDefinitionListResponse(BaseModel):
    items: list[WorkflowDefinitionResponse]
    total: int


class WorkflowNodeRunResponse(BaseModel):
    id: int | None
    workflow_run_id: str
    node_id: str
    node_type: str
    title: str
    position: int
    status: str
    input: dict[str, object]
    output: dict[str, object]
    job_ids: list[str]
    error_message: str | None
    failure_reason: FailureReason
    failure: FailureDetail | None
    created_at: str | None
    started_at: str | None
    finished_at: str | None


class WorkflowRunResponse(BaseModel):
    id: str
    name: str
    status: str
    total: int
    completed: int
    failed: int
    skipped: int
    concurrency: int
    source: str
    schedule_id: int | None
    definition_id: str | None
    failure_reason: FailureReason
    failure: FailureDetail | None
    created_at: str | None
    finished_at: str | None
    node_runs: list[WorkflowNodeRunResponse] = Field(default_factory=list)


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunResponse]
    total: int


class WorkflowDefinitionSaveResponse(BaseModel):
    definition: WorkflowDefinitionResponse
    trigger: WorkflowTriggerResponse | None = None
    run: WorkflowRunResponse | None = None


def workflow_run_response(run: WorkflowRun) -> WorkflowRunResponse:
    node_runs = [workflow_node_run_response(node_run) for node_run in run.node_runs]
    return WorkflowRunResponse(
        id=run.id,
        name=run.name,
        status=run.status,
        total=run.total,
        completed=run.completed,
        failed=run.failed,
        skipped=run.skipped,
        concurrency=run.concurrency,
        source=run.source,
        schedule_id=run.schedule_id,
        definition_id=run.definition_id,
        failure_reason=workflow_run_failure_reason(run),
        failure=workflow_run_failure_detail(run, node_runs),
        created_at=run.created_at,
        finished_at=run.finished_at,
        node_runs=node_runs,
    )


def workflow_definition_response(
    item: WorkflowDefinitionWithTriggers | WorkflowDefinition,
) -> WorkflowDefinitionResponse:
    if isinstance(item, WorkflowDefinitionWithTriggers):
        definition = item.definition
        triggers = item.triggers
    else:
        definition = item
        triggers = []
    return WorkflowDefinitionResponse(
        id=definition.id,
        name=definition.name,
        definition=definition.definition,
        triggers=[workflow_trigger_response(trigger) for trigger in triggers],
        created_at=definition.created_at,
        updated_at=definition.updated_at,
    )


def workflow_trigger_response(trigger: WorkflowTrigger) -> WorkflowTriggerResponse:
    if trigger.id is None:
        raise ValueError("workflow trigger id is required")
    return WorkflowTriggerResponse(
        id=trigger.id,
        workflow_definition_id=trigger.workflow_definition_id,
        status=trigger.status,
        schedule=trigger.schedule,
        next_run_at=trigger.next_run_at,
        last_run_at=trigger.last_run_at,
        last_success_at=trigger.last_success_at,
        last_error_code=trigger.last_error_code,
        last_error_message=trigger.last_error_message,
        created_at=trigger.created_at,
        updated_at=trigger.updated_at,
    )


def workflow_node_run_response(node_run: WorkflowNodeRun) -> WorkflowNodeRunResponse:
    return WorkflowNodeRunResponse(
        id=node_run.id,
        workflow_run_id=node_run.workflow_run_id,
        node_id=node_run.node_id,
        node_type=node_run.node_type,
        title=node_run.title,
        position=node_run.position,
        status=node_run.status,
        input=node_run.input,
        output=node_run.output,
        job_ids=node_run.job_ids,
        error_message=node_run.error_message,
        failure_reason=classify_failure_reason(
            node_run.error_message,
            node_run.status if node_run.status == "failed" else None,
        ),
        failure=workflow_node_failure_detail(node_run),
        created_at=node_run.created_at,
        started_at=node_run.started_at,
        finished_at=node_run.finished_at,
    )


def workflow_run_failure_reason(run: WorkflowRun) -> FailureReason:
    if run.status not in {"failed", "partial"}:
        return "unknown"
    for node_run in run.node_runs:
        if node_run.status != "failed":
            continue
        reason = classify_failure_reason(node_run.error_message, node_run.status)
        if reason != "unknown":
            return reason
    return classify_failure_reason(run.status)


def workflow_run_failure_detail(
    run: WorkflowRun,
    node_runs: list[WorkflowNodeRunResponse],
) -> FailureDetail | None:
    if run.status not in {"failed", "partial", "cancelled"}:
        return None
    for node_run in node_runs:
        if node_run.status == "failed" and node_run.failure is not None:
            return node_run.failure
    return failure_detail(run.status, status=run.status)


def workflow_node_failure_detail(node_run: WorkflowNodeRun) -> FailureDetail | None:
    if node_run.status not in {"failed", "cancelled"}:
        return None
    return failure_detail(
        node_run.error_message,
        node_run.status,
        code=string_option(node_run.output.get("error_code")),
        message=node_run.error_message,
        status=node_run.status,
        retryable=bool_option(node_run.output.get("error_retryable")),
    )


def string_option(value: object) -> str | None:
    return value if isinstance(value, str) else None


def bool_option(value: object) -> bool | None:
    return value if isinstance(value, bool) else None
