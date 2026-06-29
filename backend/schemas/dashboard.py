from __future__ import annotations

from pydantic import BaseModel


class DashboardLibrarySummary(BaseModel):
    artists: int
    artworks: int
    downloaded_files: int
    pending_files: int
    failed_files: int
    attention_artists: int
    artists_with_updates: int
    artists_with_failed_files: int
    unavailable_artists: int


class DashboardWorkflowSummary(BaseModel):
    running_runs: int
    failed_runs: int
    completed_runs: int
    active_schedules: int
    blocked_schedules: int
    inactive_schedules: int
    waiting_jobs: int


class DashboardJobSummary(BaseModel):
    inactive: int
    queued: int
    running: int
    completed: int
    failed: int
    cancelled: int


class DashboardSummaryResponse(BaseModel):
    library: DashboardLibrarySummary
    workflows: DashboardWorkflowSummary
    jobs: DashboardJobSummary
    queue_paused: bool
