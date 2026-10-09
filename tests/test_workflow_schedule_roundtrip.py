"""Exercise API -> real JavaScript JSON -> save API without starting any workflow."""

import json
import shutil
import subprocess
from contextlib import closing
from dataclasses import replace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.db.migrate import migrate_database
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.workflow_schedule_service import WorkflowScheduleService, next_run_time


@pytest.fixture
def schedule_api(tmp_path, monkeypatch):
    db_path = tmp_path / "roundtrip.sqlite3"
    migrate_database(db_path)
    # Run + schedule must exercise its request path without running even the synthetic definition.
    run = Mock(return_value=None)
    monkeypatch.setattr(WorkflowScheduleService, "run_definition", run)
    app = create_app(db_path=db_path, start_queue=False)
    with TestClient(app) as client:
        yield db_path, client, run


def seed(db_path, days, *, enabled=False):
    definition = AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": "JSON roundtrip",
            "nodes": [{"id": "actions", "type": "execute_actions", "config": {"download": False}}],
        }
    )
    with closing(WorkflowScheduleService(db_path)) as service:
        saved, control = service.save_with_trigger(
            definition, schedule={"type": "interval", "every": 6, "unit": "hours"}
        )
        saved, selected = service.save_with_trigger(
            definition,
            definition_id=saved.id,
            enabled=enabled,
            schedule={
                "type": "weekly",
                "time": "04:00",
                "timezone": "UTC",
                "days_of_week": days,
                "run_after_startup": True,
                "compat_workflow_trigger": {"float_option": 1.0},
            },
        )
    return saved, selected, control


def browser_save(response, trigger_id, patch):
    node = shutil.which("node")
    if node is None:
        pytest.skip("The cross-language API test requires the frontend's Node runtime")
    result = subprocess.run(
        [
            node,
            "-e",
            """
            const fs = require('node:fs');
            const input = JSON.parse(fs.readFileSync(0, 'utf8'));
            const definition = JSON.parse(input.wire).items[0];
            const trigger = definition.triggers.find(t => t.id === input.trigger_id);
            process.stdout.write(JSON.stringify({
              parsed_days: trigger.schedule.days_of_week,
              effective_days: trigger.effective_days_of_week,
              request: {
                definition_id: definition.id, definition: definition.definition,
                trigger: { trigger_id: trigger.id, enabled: trigger.status === 'active',
                  schedule_patch: input.patch, run_now: true }
              }
            }));
            """,
        ],
        input=json.dumps({"wire": response.text, "trigger_id": trigger_id, "patch": patch}),
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=10,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    "days,effective",
    [([1.0], []), ([1.0, 2, "03", True, 2.5, 7], [2, 3, 7]), ([1.0, "２"], [2])],
)
@pytest.mark.parametrize("patch", [{}, {"time": "05:00"}, {"days_of_week": [1]}])
def test_weekdays_survive_real_javascript_roundtrip(schedule_api, enabled, days, effective, patch):
    db_path, client, run = schedule_api
    saved, selected, control = seed(db_path, days, enabled=enabled)
    response = client.get("/api/workflows/definitions")
    assert response.status_code == 200
    with closing(WorkflowScheduleService(db_path)) as service:
        original_json = service.repository.conn.execute(
            "SELECT schedule_json FROM workflow_triggers WHERE id = ?", (selected.id,)
        ).fetchone()[0]

    browser = browser_save(response, selected.id, patch)
    # JavaScript demonstrably erased the float type, but only the patch crosses back.
    assert type(browser["parsed_days"][0]) is int
    assert browser["effective_days"] == effective
    assert "schedule" not in browser["request"]["trigger"]
    result = client.post("/api/workflows/definitions", json=browser["request"])
    assert result.status_code == 200
    assert result.json()["trigger"]["effective_days_of_week"] == (
        [1] if "days_of_week" in patch else effective
    )
    run.assert_called_once_with(saved.id, source="advanced_manual", trigger_id=selected.id)

    with closing(WorkflowScheduleService(db_path)) as service:
        reloaded = service.repository.get_trigger(selected.id)
        assert reloaded.schedule == {**selected.schedule, **patch}
        assert reloaded.status == selected.status
        assert type(reloaded.schedule["compat_workflow_trigger"]["float_option"]) is float
        if "days_of_week" not in patch:
            assert [type(day) for day in reloaded.schedule["days_of_week"]] == [
                type(day) for day in days
            ]
        if not patch:
            assert (
                service.repository.conn.execute(
                    "SELECT schedule_json FROM workflow_triggers WHERE id = ?", (selected.id,)
                ).fetchone()[0]
                == original_json
            )
        assert service.repository.get_trigger(control.id) == control
        base = "2026-07-01T05:30:00Z"
        assert next_run_time(reloaded.schedule, from_time=base) == next_run_time(
            {**selected.schedule, **patch}, from_time=base
        )
        if days == [1.0] and not patch:
            assert next_run_time(reloaded.schedule, from_time=base) == "2026-07-08T04:00:00Z"
            assert (
                next_run_time(
                    {**selected.schedule, "days_of_week": browser["parsed_days"]}, from_time=base
                )
                == "2026-07-06T04:00:00Z"
            )


@pytest.mark.parametrize(
    "patch,expected",
    [
        (
            {"days_of_week": []},
            {"type": "weekly", "time": "04:00", "timezone": "UTC", "days_of_week": []},
        ),
        (
            {"type": "daily", "time": "04:00", "timezone": "UTC"},
            {"type": "daily", "time": "04:00", "timezone": "UTC"},
        ),
        (
            {"type": "interval", "every": 2, "unit": "days"},
            {"type": "interval", "every": 2, "unit": "days"},
        ),
    ],
)
def test_explicit_changes_preserve_compatibility_and_clear_inapplicable_fields(
    schedule_api, patch, expected
):
    db_path, client, _run = schedule_api
    saved, selected, control = seed(db_path, [1.0, 2])
    result = client.post(
        "/api/workflows/definitions",
        json={
            "definition_id": saved.id,
            "definition": saved.definition,
            "trigger": {"trigger_id": selected.id, "enabled": False, "schedule_patch": patch},
        },
    )
    assert result.status_code == 200
    with closing(WorkflowScheduleService(db_path)) as service:
        reloaded = service.repository.get_trigger(selected.id)
        assert reloaded.schedule == {
            **expected,
            "run_after_startup": True,
            "compat_workflow_trigger": {"float_option": 1.0},
        }
        assert type(reloaded.schedule["compat_workflow_trigger"]["float_option"]) is float
        assert service.repository.get_trigger(control.id) == control


@pytest.mark.parametrize(
    "patch", [{"time": "99:00"}, {"timezone": "Unknown/Zone"}, {"type": "unknown"}]
)
def test_patch_validates_the_complete_rule_before_any_write(schedule_api, patch):
    db_path, client, run = schedule_api
    saved, selected, _control = seed(db_path, [1.0])
    result = client.post(
        "/api/workflows/definitions",
        json={
            "definition_id": saved.id,
            "definition": {**saved.definition, "name": "Do not save"},
            "trigger": {"trigger_id": selected.id, "schedule_patch": patch, "run_now": True},
        },
    )
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "validation_error"
    with closing(WorkflowScheduleService(db_path)) as service:
        assert service.repository.get_definition(saved.id) == saved
        assert service.repository.get_trigger(selected.id) == selected
    run.assert_not_called()


@pytest.mark.parametrize("invalid", ["missing_id", "wrong_definition", "both_rules", "new_trigger"])
def test_patch_rejects_unsafe_trigger_selection(schedule_api, invalid):
    db_path, client, run = schedule_api
    saved, selected, _control = seed(db_path, [1.0])
    request = {
        "definition_id": saved.id,
        "definition": {**saved.definition, "name": "Do not save"},
        "trigger": {"trigger_id": selected.id, "schedule_patch": {}, "run_now": True},
    }
    if invalid == "missing_id":
        request["trigger"]["trigger_id"] = 999
    elif invalid == "wrong_definition":
        request["definition_id"] = "other"
    elif invalid == "both_rules":
        request["trigger"]["schedule"] = selected.schedule
    else:
        del request["trigger"]["trigger_id"]
    result = client.post("/api/workflows/definitions", json=request)
    assert result.status_code == {"missing_id": 404, "wrong_definition": 400}.get(invalid, 422)
    with closing(WorkflowScheduleService(db_path)) as service:
        assert service.repository.get_definition(saved.id) == saved
        assert service.repository.get_trigger(selected.id) == selected
        assert service.repository.get_definition("other") is None
    run.assert_not_called()


def test_existing_full_schedule_requests_remain_supported(schedule_api):
    db_path, client, _run = schedule_api
    saved, selected, _control = seed(db_path, [1.0])
    result = client.post(
        "/api/workflows/definitions",
        json={
            "definition_id": saved.id,
            "definition": saved.definition,
            "trigger": {"trigger_id": selected.id, "schedule": {"type": "interval", "every": 2}},
        },
    )
    assert result.status_code == 200
    assert result.json()["trigger"]["schedule"] == {"type": "interval", "every": 2}


def test_uninterpretable_legacy_weekdays_remain_readable(schedule_api):
    db_path, client, _run = schedule_api
    _saved, selected, _control = seed(db_path, [1.0])
    with closing(WorkflowScheduleService(db_path)) as service:
        service.repository.update_trigger(
            replace(selected, schedule={**selected.schedule, "days_of_week": ["²"]})
        )
    result = client.get("/api/workflows/definitions")
    assert result.status_code == 200
    selected_response = next(
        trigger for trigger in result.json()["items"][0]["triggers"] if trigger["id"] == selected.id
    )
    assert selected_response["effective_days_of_week"] is None
    assert selected_response["schedule"]["days_of_week"] == ["²"]
