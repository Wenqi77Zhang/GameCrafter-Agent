"""Portable project archive and verified cascading deletion without external services."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime
from io import BytesIO
from typing import Any
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.models import (
    Base,
    ProjectRecord,
    SourceAssetRecord,
    StoredObjectRecord,
)
from gamecrafter.infrastructure.storage.local import LocalObjectStorage


class ProjectPortabilityError(RuntimeError):
    """Safe export or deletion error."""


class DatabaseProjectPortabilityService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: LocalObjectStorage,
        *,
        max_export_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        self._sessions = session_factory
        self._storage = storage
        self._max_export_bytes = max_export_bytes

    def export_zip(self, project_id: UUID) -> tuple[str, bytes]:
        with self._sessions() as session:
            project = session.get(ProjectRecord, project_id)
            if project is None:
                raise ProjectPortabilityError("project not found")
            selected, order = self._reachable_rows(session, project_id)
            records: dict[str, list[dict[str, Any]]] = {}
            for table in order:
                ids = selected[table.name]
                rows = session.execute(select(table).where(table.c.id.in_(ids))).mappings()
                records[table.name] = [
                    {key: self._json_value(value) for key, value in row.items()} for row in rows
                ]
            object_ids = self._object_ids(session, selected)
            objects = (
                list(
                    session.scalars(
                        select(StoredObjectRecord).where(StoredObjectRecord.id.in_(object_ids))
                    )
                )
                if object_ids
                else []
            )
            manifest = {
                "schema_version": "gamecrafter-portable-project-v1",
                "project_id": str(project.id),
                "project_slug": project.slug,
                "record_counts": {name: len(items) for name, items in records.items()},
                "objects": [
                    {
                        "object_key": item.object_key,
                        "sha256": item.sha256,
                        "size_bytes": item.size_bytes,
                        "media_type": item.media_type,
                    }
                    for item in objects
                ],
                "contains_private_material": any(
                    source.get("site_key") == "local-private"
                    for source in records.get("sources", [])
                ),
            }
            target = BytesIO()
            with ZipFile(target, "w", ZIP_DEFLATED) as archive:
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                )
                archive.writestr(
                    "records.json",
                    json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True),
                )
                total = 0
                for item in objects:
                    with self._storage.open(item.object_key) as handle:
                        payload = handle.read()
                    total += len(payload)
                    if total > self._max_export_bytes:
                        raise ProjectPortabilityError("project archive exceeded export size limit")
                    if hashlib.sha256(payload).hexdigest() != item.sha256:
                        raise ProjectPortabilityError("stored object failed export integrity check")
                    archive.writestr(f"objects/{item.object_key}", payload)
            payload = target.getvalue()
            if len(payload) > self._max_export_bytes:
                raise ProjectPortabilityError("compressed project archive exceeded size limit")
            return f"gamecrafter-{project.slug}.zip", payload

    def delete_project(self, *, project_id: UUID, confirmation: str) -> dict[str, object]:
        object_keys: list[str] = []
        with self._sessions.begin() as session:
            project = session.get(ProjectRecord, project_id)
            if project is None:
                raise ProjectPortabilityError("project not found")
            if confirmation != f"DELETE {project.slug}":
                raise ProjectPortabilityError(f'type "DELETE {project.slug}" to confirm')
            selected, order = self._reachable_rows(session, project_id)
            object_ids = self._object_ids(session, selected)
            removed_records = sum(len(ids) for ids in selected.values())
            for table in reversed(order):
                session.execute(delete(table).where(table.c.id.in_(selected[table.name])))
            for object_id in object_ids:
                references = int(
                    session.scalar(
                        select(func.count(SourceAssetRecord.id)).where(
                            SourceAssetRecord.stored_object_id == object_id
                        )
                    )
                    or 0
                )
                if references == 0:
                    stored = session.get(StoredObjectRecord, object_id)
                    if stored is not None:
                        object_keys.append(stored.object_key)
                        session.delete(stored)
        for key in object_keys:
            self._storage.delete(key)
        return {
            "deleted": True,
            "project_id": str(project_id),
            "removed_records": removed_records,
            "removed_unreferenced_objects": len(object_keys),
        }

    @staticmethod
    def _reachable_rows(session: Session, project_id: UUID):
        project_table = ProjectRecord.__table__
        selected: dict[str, set[Any]] = {project_table.name: {project_id}}
        order = [project_table]
        changed = True
        while changed:
            changed = False
            for table in Base.metadata.sorted_tables:
                if table.name in selected or "id" not in table.c:
                    continue
                for foreign_key in table.foreign_keys:
                    parent = foreign_key.column.table
                    parent_ids = selected.get(parent.name)
                    if not parent_ids:
                        continue
                    values = set(
                        session.scalars(
                            select(table.c.id).where(foreign_key.parent.in_(parent_ids))
                        )
                    )
                    if values:
                        selected[table.name] = values
                        order.append(table)
                        changed = True
                        break
        return selected, order

    @staticmethod
    def _object_ids(session: Session, selected: dict[str, set[Any]]) -> set[UUID]:
        # Stored objects are parents of source assets, so they are intentionally not included in
        # the project-descendant traversal. Read their foreign keys from exported asset rows later.
        asset_ids = selected.get("source_assets", set())
        if not asset_ids:
            return set()
        return set(
            session.scalars(
                select(SourceAssetRecord.stored_object_id).where(
                    SourceAssetRecord.id.in_(asset_ids)
                )
            )
        )

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, (UUID, datetime, date)):
            return value.isoformat() if not isinstance(value, UUID) else str(value)
        if isinstance(value, bytes):
            return {"base64": base64.b64encode(value).decode()}
        return value
