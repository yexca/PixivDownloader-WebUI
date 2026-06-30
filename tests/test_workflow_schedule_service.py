from dataclasses import replace

from backend.db.migrate import migrate_database
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.workflow_schedule_service import WorkflowScheduleService, next_run_time


def test_workflow_trigger_creates_advanced_run(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path)
    definition = AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": "Scheduled advanced workflow",
            "nodes": [
                {
                    "id": "actions",
                    "type": "execute_actions",
                    "title": "Execute actions",
                    "config": {
                        "download": False,
                        "naming_rule": "{artist}/{original_filename}",
                    },
                }
            ],
        }
    )
    service = WorkflowScheduleService(db_path)
    try:
        saved, trigger = service.save_with_trigger(
            definition,
            schedule={"type": "interval", "every": 1, "unit": "minutes"},
        )
        service.repository.update_trigger(replace(trigger, next_run_at="2000-01-01T00:00:00Z"))

        results = service.run_due_triggers()
        runs = results[0].run.node_runs if results[0].run is not None else []
    finally:
        service.close()

    assert saved.name == "Scheduled advanced workflow"
    assert len(results) == 1
    assert results[0].created is True
    assert results[0].run is not None
    assert results[0].run.source == "workflow_trigger"
    assert results[0].run.schedule_id == trigger.id
    assert [node.node_id for node in runs] == ["actions"]


def test_next_run_time_supports_interval_daily_weekly_monthly():
    base = "2026-07-01T02:30:00Z"

    assert next_run_time(
        {"type": "interval", "every": 6, "unit": "hours"},
        from_time=base,
    ) == "2026-07-01T08:30:00Z"
    assert next_run_time({"type": "daily", "time": "03:00"}, from_time=base) == (
        "2026-07-01T03:00:00Z"
    )
    assert next_run_time(
        {"type": "weekly", "days_of_week": [3], "time": "02:00"},
        from_time=base,
    ) == "2026-07-08T02:00:00Z"
    assert next_run_time(
        {"type": "monthly", "day": "last", "time": "04:00"},
        from_time=base,
    ) == "2026-07-31T04:00:00Z"
