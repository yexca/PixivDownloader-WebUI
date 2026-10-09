"""Pin the target semantics used by the advanced editor's read/save conversion."""

from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.db.migrate import migrate_database
from backend.domain.entities import Artist
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.tag_repository import LocalTagRepository
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.workflow_nodes.target import resolve_artist_ids, resolve_artwork_ids
from backend.services.workflow_schedule_service import WorkflowScheduleService


@pytest.fixture
def target_db(tmp_path):
    db_path = tmp_path / "targets.sqlite3"
    migrate_database(db_path)
    with closing(ArtistRepository(db_path)) as artists:
        for artist_id, days, status in [
            ("1", 90, "available"),
            ("2", 10, "unavailable"),
            ("3", 1, "available"),
            ("4", None, "available"),
            ("5", 45, "available"),
        ]:
            artists.upsert(
                Artist(
                    id=artist_id,
                    name=artist_id,
                    account_status=status,
                    last_checked_at=(datetime.now(UTC) - timedelta(days=days)).isoformat()
                    if days is not None
                    else None,
                )
            )
        # Upsert timestamps new rows; seed the never-checked case in this test DB.
        with artists.conn:
            artists.conn.execute("UPDATE artists SET last_checked_at = NULL WHERE id = ?", ("4",))
    with closing(LocalTagRepository(db_path)) as tags:
        for artist_id, values in [
            ("1", ["cat"]),
            ("2", ["dog"]),
            ("3", ["bird"]),
            ("4", ["cat", "dog"]),
            ("5", ["big cat", "red,blue"]),
        ]:
            tags.set_artist_tags(artist_id, values)
    return db_path


@pytest.mark.parametrize("scope", ["tagged", "artists_with_tag"])
@pytest.mark.parametrize(
    "tag_config,expected",
    [
        ({"tags": ["cat", "dog"]}, {"1", "2", "4"}),
        ({"tag": "bird", "tags": ["cat", "dog"]}, {"1", "2", "3", "4"}),
        ({"tag": "cat", "tags": ["cat", "dog", "cat"]}, {"1", "2", "4"}),
        ({"tag": "cat"}, {"1", "4"}),
        ({"tags": ["big cat", "red,blue"]}, {"5"}),
        ({"tag": "", "tags": []}, set()),
    ],
)
def test_tag_and_tags_are_a_union_with_deduplicated_artists(target_db, scope, tag_config, expected):
    config = {"scope": scope, "skip_unavailable_artists": False, **tag_config}
    assert set(resolve_artist_ids(config, target_db)) == expected
    assert resolve_artwork_ids(config) == []


@pytest.mark.parametrize(
    "config,artists,artworks",
    [
        ({"artist_ids": ["1"]}, ["1"], []),
        ({"scope": "selected", "artist_id": "1", "artist_ids": ["3"]}, ["1", "3"], []),
        (
            {"scope": "single_artist", "artist_id": "1", "artist_ids": ["3"]},
            ["1"],
            [],
        ),
        ({"scope": "single_artist", "artist_ids": ["1", "3"]}, ["1", "3"], []),
        ({"scope": "single_artist", "artist_id": "", "artist_ids": []}, [], []),
        (
            {
                "scope": "artists",
                "artist_source": "artist_ids",
                "artist_ids": ["1"],
                "artwork_ids": ["100"],
            },
            ["1"],
            [],
        ),
        (
            {
                "scope": "artists",
                "artist_source": "artwork_ids",
                "artist_ids": ["1"],
                "artwork_ids": ["100"],
            },
            [],
            ["100"],
        ),
        ({"scope": "single_artwork", "artwork_id": "100", "artwork_ids": ["200"]}, [], ["100"]),
        ({"scope": "artworks", "artwork_id": "100", "artwork_ids": ["200"]}, [], ["100", "200"]),
        ({"scope": "selected", "artist_ids": ["1"], "artwork_ids": ["100"]}, ["1"], ["100"]),
    ],
)
def test_explicit_target_scopes_and_artist_source(target_db, config, artists, artworks):
    assert resolve_artist_ids(config, target_db) == artists
    assert resolve_artwork_ids(config) == artworks


def test_target_options_apply_after_the_complete_tag_union(target_db):
    config = {
        "scope": "artists_with_tag",
        "tag": "bird",
        "tags": ["cat", "dog"],
        "artist_selection": "newest_checked_first",
        "skip_unavailable_artists": False,
        "max_artists": 2,
    }
    assert resolve_artist_ids(config, target_db) == ["3", "2"]
    config["skip_unavailable_artists"] = True
    assert resolve_artist_ids(config, target_db) == ["3", "1"]
    config["filters"] = [{"type": "last_checked_before_days", "days": 30}]
    assert resolve_artist_ids(config, target_db) == ["1", "4"]


@pytest.mark.parametrize("day_field", ["days", "stale_days"])
def test_stale_day_aliases_and_absent_limit_keep_backend_defaults(target_db, day_field):
    config = {"scope": "artists_not_checked", day_field: 30}
    assert set(resolve_artist_ids(config, target_db)) == {"1", "4", "5"}
    config["max_artists"] = None
    assert set(resolve_artist_ids(config, target_db)) == {"1", "4", "5"}


@pytest.mark.parametrize("status", ["active", "paused"])
def test_definition_only_save_preserves_other_nodes_and_existing_triggers(target_db, status):
    definition = AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": "Legacy workflow",
            "metadata": {"legacy": True},
            "nodes": [
                {
                    "id": "legacy-target",
                    "type": "artist_target",
                    "config": {"scope": "artists_with_tag", "tag": "bird", "tags": ["cat", "dog"]},
                },
                {"id": "sync", "type": "sync_metadata", "config": {"mode": "none"}},
                {
                    "id": "actions",
                    "type": "execute_actions",
                    "config": {
                        "download": False,
                        "tag_variants": [{"tag": "cat", "behavior": "skip"}],
                    },
                },
            ],
        }
    )
    with closing(WorkflowScheduleService(target_db)) as service:
        saved, trigger = service.save_with_trigger(
            definition,
            enabled=status == "active",
            schedule={"type": "interval", "every": 6, "unit": "hours", "run_after_startup": True},
        )
        second = service.repository.create_trigger(
            replace(
                trigger,
                id=None,
                schedule={"type": "daily", "time": "03:00", "timezone": "Asia/Tokyo"},
            )
        )
        original_triggers = service.repository.list_triggers(saved.id)
        definition.nodes[0].config["tags"] = ["cat", "dog", "big cat"]
        edited = service.save_definition(definition, definition_id=saved.id)
        assert edited.definition == definition.model_dump(mode="json")
        assert service.repository.list_triggers(saved.id) == original_triggers
        assert len(original_triggers) == 2
        assert second.id != trigger.id
