from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.repositories._time import utc_now


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

    def close(self) -> None:
        self.conn.close()

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


def candidate_sort_expression(sort_order: str) -> str:
    if sort_order == "oldest_first":
        return "sort_key ASC, artworks.id ASC"
    if sort_order == "local_order":
        return "artworks.discovered_at ASC, artworks.id ASC"
    return "sort_key DESC, artworks.id DESC"
