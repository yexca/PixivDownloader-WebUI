from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.domain.entities import Artwork, ArtworkFile
from backend.repositories._time import utc_now
from backend.repositories.artwork_repository import artwork_from_row
from backend.repositories.file_repository import artwork_file_from_row


@dataclass(frozen=True)
class WorkflowCandidateSet:
    id: str
    workflow_run_id: str
    source: str
    sort_order: str
    total_count: int = 0
    workflow_node_run_id: int | None = None
    config: dict[str, object] = field(default_factory=dict)
    created_at: str | None = None


@dataclass(frozen=True)
class CollectArtworkCandidatesRequest:
    workflow_run_id: str
    workflow_node_run_id: int | None
    artist_ids: list[str]
    source: str
    sort_order: str
    limit: int | None = None
    min_artwork_id: str | None = None
    max_artwork_id: str | None = None
    config: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class FilterArtworkCandidatesRequest:
    workflow_run_id: str
    workflow_node_run_id: int | None
    source_set_id: str
    ai: str = "include"
    required_tags: list[str] = field(default_factory=list)
    blocked_tags: list[str] = field(default_factory=list)
    stop_above_limit: int | None = None
    config: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class FilterArtworkCandidatesResult:
    candidate_set: WorkflowCandidateSet
    source_count: int
    stopped_by_rule: bool = False


class WorkflowCandidateRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def collect_artwork_candidates(
        self,
        request: CollectArtworkCandidatesRequest,
    ) -> WorkflowCandidateSet:
        set_id = str(uuid.uuid4())
        created_at = utc_now()
        rows = self._candidate_rows(request)
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO workflow_candidate_sets(
                        id, workflow_run_id, workflow_node_run_id, source,
                        sort_order, total_count, config_json, created_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        set_id,
                        request.workflow_run_id,
                        request.workflow_node_run_id,
                        request.source,
                        request.sort_order,
                        len(rows),
                        json.dumps(request.config),
                        created_at,
                    ),
                )
                self.conn.executemany(
                    """
                    INSERT INTO workflow_candidate_artworks(
                        set_id, artist_id, artwork_id, source, position, sort_key, created_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            set_id,
                            str(row["artist_id"]),
                            str(row["artwork_id"]),
                            request.source,
                            index,
                            int(row["sort_key"]) if row["sort_key"] is not None else None,
                            created_at,
                        )
                        for index, row in enumerate(rows)
                    ],
                )
        except sqlite3.Error as exc:
            raise DatabaseError("failed to collect workflow candidates") from exc
        return WorkflowCandidateSet(
            id=set_id,
            workflow_run_id=request.workflow_run_id,
            workflow_node_run_id=request.workflow_node_run_id,
            source=request.source,
            sort_order=request.sort_order,
            total_count=len(rows),
            config=request.config,
            created_at=created_at,
        )

    def count_artworks(self, set_id: str) -> int:
        try:
            row = self.conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM workflow_candidate_artworks
                WHERE set_id = ?
                """,
                (set_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to count workflow candidates for {set_id}") from exc
        return int(row["total"] if row is not None else 0)

    def filter_artwork_candidates(
        self,
        request: FilterArtworkCandidatesRequest,
    ) -> FilterArtworkCandidatesResult:
        source_set = self.get_candidate_set(request.source_set_id)
        candidate_source = (
            str(source_set.config.get("candidate_source") or source_set.config.get("collect_mode"))
            if source_set is not None
            else "filtered_artworks"
        )
        source_count = self.count_artworks(request.source_set_id)
        stopped_by_rule = (
            request.stop_above_limit is not None and source_count > request.stop_above_limit
        )
        rows = [] if stopped_by_rule else self._filtered_candidate_rows(request)
        candidate_set = self._create_set_from_rows(
            workflow_run_id=request.workflow_run_id,
            workflow_node_run_id=request.workflow_node_run_id,
            source="filtered_artworks",
            sort_order=source_set.sort_order if source_set is not None else "source_order",
            config={**request.config, "candidate_source": candidate_source},
            rows=rows,
        )
        return FilterArtworkCandidatesResult(
            candidate_set=candidate_set,
            source_count=source_count,
            stopped_by_rule=stopped_by_rule,
        )

    def get_candidate_set(self, set_id: str) -> WorkflowCandidateSet | None:
        try:
            row = self.conn.execute(
                """
                SELECT * FROM workflow_candidate_sets
                WHERE id = ?
                """,
                (set_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch workflow candidate set {set_id}") from exc
        if row is None:
            return None
        config_json = row["config_json"]
        return WorkflowCandidateSet(
            id=str(row["id"]),
            workflow_run_id=str(row["workflow_run_id"]),
            workflow_node_run_id=(
                int(row["workflow_node_run_id"])
                if row["workflow_node_run_id"] is not None
                else None
            ),
            source=str(row["source"]),
            sort_order=str(row["sort_order"]),
            total_count=int(row["total_count"]),
            config=json.loads(config_json) if config_json else {},
            created_at=str(row["created_at"]),
        )

    def list_artwork_ids(self, set_id: str) -> list[str]:
        try:
            rows = self.conn.execute(
                """
                SELECT artwork_id
                FROM workflow_candidate_artworks
                WHERE set_id = ?
                ORDER BY position
                """,
                (set_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list workflow candidate ids for {set_id}") from exc
        return [str(row["artwork_id"]) for row in rows]

    def list_artist_ids(self, set_id: str) -> list[str]:
        try:
            rows = self.conn.execute(
                """
                SELECT artist_id
                FROM workflow_candidate_artworks
                WHERE set_id = ?
                GROUP BY artist_id
                ORDER BY MIN(position)
                """,
                (set_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list workflow candidate artists for {set_id}") from exc
        return [str(row["artist_id"]) for row in rows]

    def list_artworks(
        self,
        set_id: str,
        *,
        artist_id: str | None = None,
    ) -> list[Artwork]:
        params: list[object] = [set_id]
        artist_filter = ""
        if artist_id is not None:
            artist_filter = "AND candidates.artist_id = ?"
            params.append(artist_id)
        try:
            rows = self.conn.execute(
                f"""
                SELECT artworks.*
                FROM workflow_candidate_artworks AS candidates
                JOIN artworks ON artworks.id = candidates.artwork_id
                WHERE candidates.set_id = ?
                  {artist_filter}
                ORDER BY candidates.position
                """,
                params,
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list workflow candidate artworks for {set_id}") from exc
        return [artwork_from_row(row) for row in rows]

    def list_files_for_artwork(
        self,
        artwork_id: str,
        *,
        candidate_source: str,
    ) -> list[ArtworkFile]:
        statuses = file_statuses_for_candidate_source(candidate_source)
        status_filter = ""
        params: list[object] = [artwork_id]
        if statuses is not None:
            status_filter = "AND status IN (" + ",".join("?" for _ in statuses) + ")"
            params.extend(statuses)
        try:
            rows = self.conn.execute(
                f"""
                SELECT *
                FROM artwork_files
                WHERE artwork_id = ?
                  {status_filter}
                ORDER BY page_index
                """,
                params,
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list candidate files for artwork {artwork_id}") from exc
        return [artwork_file_from_row(row) for row in rows]

    def close(self) -> None:
        self.conn.close()

    def _create_set_from_rows(
        self,
        *,
        workflow_run_id: str,
        workflow_node_run_id: int | None,
        source: str,
        sort_order: str,
        config: dict[str, object],
        rows: list[sqlite3.Row],
    ) -> WorkflowCandidateSet:
        set_id = str(uuid.uuid4())
        created_at = utc_now()
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO workflow_candidate_sets(
                        id, workflow_run_id, workflow_node_run_id, source,
                        sort_order, total_count, config_json, created_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        set_id,
                        workflow_run_id,
                        workflow_node_run_id,
                        source,
                        sort_order,
                        len(rows),
                        json.dumps(config),
                        created_at,
                    ),
                )
                self.conn.executemany(
                    """
                    INSERT INTO workflow_candidate_artworks(
                        set_id, artist_id, artwork_id, source, position, sort_key, created_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            set_id,
                            str(row["artist_id"]),
                            str(row["artwork_id"]),
                            source,
                            index,
                            int(row["sort_key"]) if row["sort_key"] is not None else None,
                            created_at,
                        )
                        for index, row in enumerate(rows)
                    ],
                )
        except sqlite3.Error as exc:
            raise DatabaseError("failed to create workflow candidate set") from exc
        return WorkflowCandidateSet(
            id=set_id,
            workflow_run_id=workflow_run_id,
            workflow_node_run_id=workflow_node_run_id,
            source=source,
            sort_order=sort_order,
            total_count=len(rows),
            config=config,
            created_at=created_at,
        )

    def _candidate_rows(self, request: CollectArtworkCandidatesRequest) -> list[sqlite3.Row]:
        if not request.artist_ids:
            return []
        where = ["artworks.artist_id IN (" + ",".join("?" for _ in request.artist_ids) + ")"]
        params: list[object] = [*request.artist_ids]
        self._add_source_filter(where, request.source)
        if request.min_artwork_id:
            where.append("artworks.id GLOB '[0-9]*' AND CAST(artworks.id AS INTEGER) >= ?")
            params.append(int(request.min_artwork_id))
        if request.max_artwork_id:
            where.append("artworks.id GLOB '[0-9]*' AND CAST(artworks.id AS INTEGER) <= ?")
            params.append(int(request.max_artwork_id))

        order_by = candidate_sort_expression(request.sort_order)
        limit_sql = ""
        if request.limit is not None:
            limit_sql = "LIMIT ?"
            params.append(request.limit)

        try:
            return self.conn.execute(
                f"""
                SELECT DISTINCT
                    artworks.artist_id,
                    artworks.id AS artwork_id,
                    CASE
                        WHEN artworks.id GLOB '[0-9]*' THEN CAST(artworks.id AS INTEGER)
                        ELSE NULL
                    END AS sort_key,
                    artworks.discovered_at
                FROM artworks
                JOIN artists ON artists.id = artworks.artist_id
                WHERE {" AND ".join(where)}
                ORDER BY {order_by}
                {limit_sql}
                """,
                params,
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to query workflow candidate artworks") from exc

    def _filtered_candidate_rows(
        self,
        request: FilterArtworkCandidatesRequest,
    ) -> list[sqlite3.Row]:
        where = ["candidates.set_id = ?"]
        params: list[object] = [request.source_set_id]
        add_ai_filter(where, request.ai)
        for tag in request.required_tags:
            where.append(tag_exists_sql())
            params.append(tag)
        for tag in request.blocked_tags:
            where.append(f"NOT {tag_exists_sql()}")
            params.append(tag)
        try:
            return self.conn.execute(
                f"""
                SELECT
                    candidates.artist_id,
                    candidates.artwork_id,
                    candidates.sort_key
                FROM workflow_candidate_artworks AS candidates
                JOIN artworks ON artworks.id = candidates.artwork_id
                WHERE {" AND ".join(where)}
                ORDER BY candidates.position
                """,
                params,
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to filter workflow candidate artworks") from exc

    def _add_source_filter(self, where: list[str], source: str) -> None:
        if source == "new_since_last_download":
            where.append(
                """
                artworks.id GLOB '[0-9]*'
                AND CAST(artworks.id AS INTEGER) >
                    CAST(COALESCE(artists.latest_downloaded_artwork_id, '0') AS INTEGER)
                """
            )
            return
        if source == "pending_files":
            where.append(file_status_exists("pending", "remote_only"))
            return
        if source == "failed_files":
            where.append(file_status_exists("failed"))
            return
        if source == "all_synced":
            return
        raise ValueError(f"unsupported collect source: {source}")


def file_status_exists(*statuses: str) -> str:
    quoted = ", ".join(f"'{status}'" for status in statuses)
    return f"""
        EXISTS (
            SELECT 1 FROM artwork_files
            WHERE artwork_files.artwork_id = artworks.id
              AND artwork_files.status IN ({quoted})
        )
    """


AI_TAGS = (
    "ai",
    "ai-generated",
    "ai生成",
    "ai生成作品",
    "aiイラスト",
    "ai生成イラスト",
    "ai 画作",
    "ai 생성",
)


def add_ai_filter(where: list[str], ai_mode: str) -> None:
    if ai_mode == "exclude":
        where.append(f"NOT {ai_tag_exists_sql()}")
    if ai_mode == "only":
        where.append(ai_tag_exists_sql())


def tag_exists_sql() -> str:
    return """
        EXISTS (
            SELECT 1 FROM json_each(artworks.tags_json)
            WHERE lower(CAST(json_each.value AS TEXT)) = lower(?)
        )
    """


def ai_tag_exists_sql() -> str:
    quoted_tags = ", ".join(sql_quote(tag.casefold()) for tag in AI_TAGS)
    return f"""
        EXISTS (
            SELECT 1 FROM json_each(artworks.tags_json)
            WHERE lower(CAST(json_each.value AS TEXT)) IN ({quoted_tags})
        )
    """


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def candidate_sort_expression(sort_order: str) -> str:
    if sort_order == "oldest_first":
        return "sort_key ASC, artworks.id ASC"
    if sort_order == "local_order":
        return "artworks.discovered_at ASC, artworks.id ASC"
    return "sort_key DESC, artworks.id DESC"


def file_statuses_for_candidate_source(source: str) -> tuple[str, ...] | None:
    if source == "failed_files":
        return ("failed",)
    if source in {"pending_files", "new_since_last_download"}:
        return ("remote_only", "pending")
    return None
