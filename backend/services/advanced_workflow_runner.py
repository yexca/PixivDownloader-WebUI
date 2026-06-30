from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path

from backend.repositories._time import utc_now
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_run_repository import (
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunItem,
    WorkflowRunRepository,
)
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.job_service import JobService, WorkflowJobLink

ACTIVE_JOB_STATUSES = {"inactive", "queued", "running"}
FAILED_JOB_STATUSES = {"failed", "cancelled"}


class AdvancedWorkflowRunner:
    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        settings_json_path: Path | str | None = None,
    ) -> None:
        self.db_path = db_path
        self.settings_json_path = settings_json_path
        self.repository = WorkflowRunRepository(db_path)

    def create_run(self, definition: AdvancedWorkflowDefinitionRequest) -> WorkflowRun:
        if not definition.nodes:
            raise ValueError("advanced workflow requires at least one node")
        now = utc_now()
        run = WorkflowRun(
            id=str(uuid.uuid4()),
            status="running",
            total=len(definition.nodes),
            completed=0,
            failed=0,
            skipped=0,
            concurrency=1,
            source="advanced",
            created_at=now,
        )
        self.repository.create_run(run)
        item_id = self.repository.create_item(
            WorkflowRunItem(
                id=None,
                run_id=run.id,
                draft_id=f"advanced:{run.id}",
                title=definition.name or "Advanced workflow",
                status="running",
                config=definition.model_dump(mode="json"),
                request={"source": "advanced", "definition": definition.model_dump(mode="json")},
                created_at=now,
            )
        )
        for position, node in enumerate(definition.nodes):
            self.repository.create_node_run(
                WorkflowNodeRun(
                    id=None,
                    workflow_run_id=run.id,
                    node_id=node.id,
                    node_type=node.type,
                    title=node.title or node.type.replace("_", " ").title(),
                    position=position,
                    status="pending",
                    input={"config": node.config},
                    created_at=now,
                )
            )
        run = self.repository.get_run(run.id) or run
        return self.process_run(run.id, item_id=item_id)

    def process_run(self, run_id: str, *, item_id: int | None = None) -> WorkflowRun:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"workflow run not found: {run_id}")
        if run.source != "advanced":
            return run

        context: dict[str, object] = {}
        previous_output: dict[str, object] = {}
        for node_run in self.repository.list_node_runs(run.id):
            if node_run.status == "completed":
                previous_output = node_run.output
                context.update(node_run.output)
                continue
            if node_run.status == "failed":
                break
            if node_run.status == "running" and node_run.job_ids:
                refreshed = self._refresh_node_jobs(node_run)
                if refreshed.status != "completed":
                    break
                node_run = refreshed
                previous_output = node_run.output
                context.update(node_run.output)
                continue
            node_run = replace(
                node_run,
                status="running",
                started_at=node_run.started_at or utc_now(),
                input={**node_run.input, "previous": previous_output},
            )
            self.repository.update_node_run(node_run)
            try:
                node_run = self._execute_node(node_run, context, item_id=item_id)
            except Exception as exc:
                failed = replace(
                    node_run,
                    status="failed",
                    error_message=str(exc),
                    finished_at=utc_now(),
                )
                self.repository.update_node_run(failed)
                break
            if node_run.status == "running":
                break
            previous_output = node_run.output
            context.update(node_run.output)

        return self._refresh_run(run.id)

    def close(self) -> None:
        self.repository.close()

    def _execute_node(
        self,
        node_run: WorkflowNodeRun,
        context: dict[str, object],
        *,
        item_id: int | None,
    ) -> WorkflowNodeRun:
        config = dict_option(node_run.input.get("config"))
        if node_run.node_type == "artist_target":
            output = {
                "artist_ids": string_list(config.get("artist_ids")),
                "artwork_ids": string_list(config.get("artwork_ids")),
                "target_scope": str(config.get("scope") or "selected"),
                "max_artists": positive_int(config.get("max_artists")),
            }
            return self._complete(node_run, output)
        if node_run.node_type == "sync_metadata":
            output = {
                "sync_mode": str(config.get("mode") or "incremental"),
            }
            return self._complete(node_run, output)
        if node_run.node_type == "collect_artworks":
            output = {
                "collect_mode": str(config.get("mode") or "new"),
                "max_artworks": positive_int(config.get("max_artworks")),
                "min_artwork_id": string_or_none(config.get("min_artwork_id")),
                "max_artwork_id": string_or_none(config.get("max_artwork_id")),
            }
            return self._complete(node_run, output)
        if node_run.node_type == "filter_artworks":
            output = {
                "filters": config,
            }
            return self._complete(node_run, output)
        if node_run.node_type == "execute_actions":
            return self._start_action_jobs(node_run, config, context, item_id=item_id)
        if node_run.node_type == "file_output":
            output = {
                "naming_rule": string_or_none(config.get("naming_rule")),
                "summary": "Workflow output recorded.",
            }
            return self._complete(node_run, output)
        return self._complete(node_run, {"ignored": True})

    def _start_action_jobs(
        self,
        node_run: WorkflowNodeRun,
        config: dict[str, object],
        context: dict[str, object],
        *,
        item_id: int | None,
    ) -> WorkflowNodeRun:
        artist_ids = tuple(string_list(context.get("artist_ids")))
        artwork_ids = tuple(string_list(context.get("artwork_ids")))
        actions = tuple(action_list(config.get("actions")))
        if not artist_ids and not artwork_ids:
            return self._complete(node_run, {"job_ids": [], "message": "No artist targets."})
        download_options = {
            "full_download": context.get("collect_mode") == "all_local",
            "pending_only": context.get("collect_mode") == "new",
            "max_artworks": context.get("max_artworks"),
            "min_artwork_id": context.get("min_artwork_id"),
            "max_artwork_id": context.get("max_artwork_id"),
            "naming_rule": config.get("naming_rule") or context.get("naming_rule"),
            "stop_if_artwork_count_above": dict_option(context.get("filters")).get(
                "stop_above_limit"
            ),
        }
        service = JobService(self.db_path, settings_json_path=self.settings_json_path)
        try:
            job = service.create_resolve_artist_targets_job(
                artist_ids=artist_ids,
                artwork_ids=artwork_ids,
                actions=actions,
                download_options=download_options,
                max_targets_per_run=positive_int(context.get("max_artists")) or max(
                    1,
                    len(artist_ids) + len(artwork_ids),
                ),
                options=download_options,
                workflow_link=WorkflowJobLink(
                    run_id=node_run.workflow_run_id,
                    item_id=item_id,
                    source="advanced_workflow",
                ),
            )
        finally:
            service.close()
        job_ids = [] if job is None else [job.id]
        if not job_ids:
            return self._complete(node_run, {"job_ids": []})
        updated = replace(
            node_run,
            status="running",
            job_ids=job_ids,
            output={"job_ids": job_ids, "actions": list(actions)},
        )
        self.repository.update_node_run(updated)
        self._sync_item_jobs(node_run.workflow_run_id, item_id, job_ids)
        return updated

    def _refresh_node_jobs(self, node_run: WorkflowNodeRun) -> WorkflowNodeRun:
        repository = JobRepository(self.db_path)
        try:
            jobs = repository.list_by_ids(node_run.job_ids)
        finally:
            repository.close()
        if len(jobs) != len(node_run.job_ids):
            failed = replace(
                node_run,
                status="failed",
                error_message="Workflow node cannot be resolved: a linked job is missing.",
                finished_at=utc_now(),
            )
            self.repository.update_node_run(failed)
            return failed
        if any(job.status in ACTIVE_JOB_STATUSES for job in jobs):
            return node_run
        if any(job.status in FAILED_JOB_STATUSES for job in jobs):
            message = next((job.error_message for job in jobs if job.error_message), None)
            failed = replace(
                node_run,
                status="failed",
                error_message=message or node_run.error_message,
                finished_at=utc_now(),
            )
            self.repository.update_node_run(failed)
            return failed
        output = {
            **node_run.output,
            "completed_jobs": [job.id for job in jobs],
        }
        return self._complete(node_run, output)

    def _complete(self, node_run: WorkflowNodeRun, output: dict[str, object]) -> WorkflowNodeRun:
        completed = replace(
            node_run,
            status="completed",
            output=output,
            error_message=None,
            finished_at=utc_now(),
        )
        self.repository.update_node_run(completed)
        return completed

    def _refresh_run(self, run_id: str) -> WorkflowRun:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"workflow run not found: {run_id}")
        node_runs = self.repository.list_node_runs(run.id)
        completed = sum(1 for node in node_runs if node.status == "completed")
        failed = sum(1 for node in node_runs if node.status == "failed")
        skipped = sum(1 for node in node_runs if node.status == "skipped")
        has_active = any(node.status in {"pending", "running"} for node in node_runs)
        status = advanced_run_status(
            completed=completed,
            failed=failed,
            skipped=skipped,
            running=has_active,
        )
        refreshed = replace(
            run,
            status=status,
            total=len(node_runs),
            completed=completed,
            failed=failed,
            skipped=skipped,
            finished_at=None if has_active else run.finished_at or utc_now(),
            node_runs=node_runs,
        )
        self.repository.update_run(refreshed)
        for item in run.items:
            self.repository.update_item(
                replace(
                    item,
                    status="running" if has_active else status,
                    finished_at=None if has_active else item.finished_at or utc_now(),
                )
            )
        return self.repository.get_run(run_id) or refreshed

    def _sync_item_jobs(self, run_id: str, item_id: int | None, job_ids: list[str]) -> None:
        if item_id is None:
            return
        for item in self.repository.list_items(run_id):
            if item.id != item_id:
                continue
            merged = dedupe([*item.job_ids, *job_ids])
            self.repository.update_item(replace(item, status="running", job_ids=merged))
            break


def dict_option(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def action_list(value: object) -> list[str]:
    valid_actions = {"download_artist", "sync_artist", "retry_failed_artist"}
    actions = [action for action in string_list(value) if action in valid_actions]
    return actions or ["download_artist"]


def string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def advanced_run_status(
    *,
    completed: int,
    failed: int,
    skipped: int,
    running: bool = False,
) -> str:
    if running:
        return "running"
    if failed and completed:
        return "partial"
    if failed and not completed:
        return "failed"
    if skipped and not completed:
        return "skipped"
    return "completed"
