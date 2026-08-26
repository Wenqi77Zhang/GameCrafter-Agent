"""Portable project archive and verified cascading deletion without external services."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from datetime import date, datetime
from io import BytesIO
from typing import Any
from uuid import UUID
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from sqlalchemy import Date, DateTime, LargeBinary, Uuid, delete, func, insert, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from gamecrafter.infrastructure.database.models import (
    Base,
    ProjectRecord,
    SourceAssetRecord,
    StoredObjectRecord,
)
from gamecrafter.infrastructure.storage.local import LocalObjectStorage

DEFAULT_PORTABLE_ARCHIVE_MAX_BYTES = 100 * 1024 * 1024


class ProjectPortabilityError(RuntimeError):
    """Safe export or deletion error."""


class DatabaseProjectPortabilityService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: LocalObjectStorage,
        *,
        max_export_bytes: int = DEFAULT_PORTABLE_ARCHIVE_MAX_BYTES,
        max_archive_entries: int = 10_000,
    ) -> None:
        self._sessions = session_factory
        self._storage = storage
        self._max_export_bytes = max_export_bytes
        self._max_archive_entries = max_archive_entries

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
                "schema_version": "gamecrafter-portable-project-v2",
                "project_id": str(project.id),
                "project_slug": project.slug,
                "record_counts": {name: len(items) for name, items in records.items()},
                "objects": [
                    {
                        "id": str(item.id),
                        "object_key": item.object_key,
                        "sha256": item.sha256,
                        "size_bytes": item.size_bytes,
                        "media_type": item.media_type,
                        "storage_backend": item.storage_backend,
                        "created_at": item.created_at.isoformat(),
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

    def restore_zip(
        self,
        payload: bytes,
        *,
        owner_user_id: UUID | None = None,
        team_id: UUID | None = None,
    ) -> dict[str, object]:
        """Restore one verified v2 archive without trusting filenames or archive metadata."""

        if not payload or len(payload) > self._max_export_bytes:
            raise ProjectPortabilityError("project archive is empty or exceeds the size limit")
        manifest, records, object_payloads = self._read_archive(payload)
        project_id = self._uuid(manifest.get("project_id"), "manifest project id")
        project_rows = records.get("projects", [])
        if (
            len(project_rows) != 1
            or self._uuid(project_rows[0].get("id"), "project id") != project_id
        ):
            raise ProjectPortabilityError("archive must contain exactly its declared project")
        if manifest.get("project_slug") != project_rows[0].get("slug"):
            raise ProjectPortabilityError("archive project slug does not match its manifest")

        unknown = set(records) - self._project_descendant_table_names()
        if unknown:
            raise ProjectPortabilityError("archive contains unsupported database tables")
        expected_counts = manifest.get("record_counts")
        actual_counts = {name: len(items) for name, items in records.items()}
        if not isinstance(expected_counts, dict) or expected_counts != actual_counts:
            raise ProjectPortabilityError("archive record counts failed verification")
        for name, items in records.items():
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise ProjectPortabilityError(f"archive table {name} has invalid records")

        created_keys: set[str] = set()
        try:
            with self._sessions.begin() as session:
                if session.get(ProjectRecord, project_id) is not None:
                    raise ProjectPortabilityError("project id already exists")
                slug = str(project_rows[0].get("slug", ""))
                if session.scalar(select(ProjectRecord.id).where(ProjectRecord.slug == slug)):
                    raise ProjectPortabilityError("project slug already exists")

                object_id_map: dict[UUID, UUID] = {}
                for item in manifest["objects"]:
                    archived_id = self._uuid(item.get("id"), "stored object id")
                    digest = str(item.get("sha256", ""))
                    key = str(item.get("object_key", ""))
                    content = object_payloads[key]
                    existing = session.scalar(
                        select(StoredObjectRecord).where(StoredObjectRecord.sha256 == digest)
                    )
                    if existing is not None:
                        if (
                            existing.object_key != key
                            or existing.size_bytes != len(content)
                            or existing.media_type != item.get("media_type")
                        ):
                            raise ProjectPortabilityError(
                                "stored object metadata conflicts with local data"
                            )
                        object_id_map[archived_id] = existing.id
                        continue
                    id_collision = session.get(StoredObjectRecord, archived_id)
                    if id_collision is not None:
                        raise ProjectPortabilityError("stored object id conflicts with local data")
                    existed = self._storage.exists(key)
                    stored = self._storage.put(
                        BytesIO(content),
                        media_type=str(item.get("media_type")),
                        max_bytes=self._max_export_bytes,
                    )
                    if stored.key != key or stored.digest.value != digest:
                        raise ProjectPortabilityError(
                            "stored object key failed content verification"
                        )
                    if not existed:
                        created_keys.add(key)
                    session.add(
                        StoredObjectRecord(
                            id=archived_id,
                            object_key=key,
                            sha256=digest,
                            size_bytes=len(content),
                            media_type=str(item.get("media_type")),
                            storage_backend=str(item.get("storage_backend", "filesystem")),
                            created_at=datetime.fromisoformat(str(item.get("created_at"))),
                        )
                    )
                    object_id_map[archived_id] = archived_id

                for table in Base.metadata.sorted_tables:
                    table_rows = records.get(table.name)
                    if not table_rows:
                        continue
                    values = [self._database_row(table, item) for item in table_rows]
                    if table.name == "projects":
                        values[0]["owner_user_id"] = owner_user_id
                        values[0]["team_id"] = team_id
                    if table.name == "source_assets":
                        for value in values:
                            old_id = value.get("stored_object_id")
                            if old_id not in object_id_map:
                                raise ProjectPortabilityError(
                                    "source asset references a missing object"
                                )
                            value["stored_object_id"] = object_id_map[old_id]
                    session.execute(insert(table), values)
            return {
                "restored": True,
                "project_id": str(project_id),
                "project_slug": str(project_rows[0]["slug"]),
                "record_counts": actual_counts,
                "object_count": len(object_payloads),
            }
        except ProjectPortabilityError:
            for key in created_keys:
                self._storage.delete(key)
            raise
        except (SQLAlchemyError, TypeError, ValueError) as error:
            for key in created_keys:
                self._storage.delete(key)
            raise ProjectPortabilityError(
                "project archive records failed database validation"
            ) from error

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
            # PostgreSQL immutability triggers protect evidence during normal operation. A typed,
            # owner-authorized whole-project purge is the one intentional exception: the exact
            # descendant IDs were already resolved while constraints were active, and LOCAL keeps
            # the trigger bypass confined to this transaction.
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                session.execute(text("SET LOCAL session_replication_role = 'replica'"))
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
                if "id" not in table.c:
                    continue
                current = selected.setdefault(table.name, set())
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
                    new_values = values - current
                    if new_values:
                        current.update(new_values)
                        if table not in order:
                            order.append(table)
                        changed = True
            selected = {name: values for name, values in selected.items() if values}
        return selected, order

    def _read_archive(
        self, payload: bytes
    ) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, bytes]]:
        try:
            with ZipFile(BytesIO(payload)) as archive:
                infos = archive.infolist()
                if len(infos) > self._max_archive_entries:
                    raise ProjectPortabilityError("project archive contains too many entries")
                names = [item.filename for item in infos]
                if len(names) != len(set(names)) or {"manifest.json", "records.json"} - set(names):
                    raise ProjectPortabilityError(
                        "project archive has duplicate or missing entries"
                    )
                total = 0
                for info in infos:
                    if info.flag_bits & 0x1 or (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ProjectPortabilityError(
                            "encrypted or linked archive entries are not allowed"
                        )
                    if info.filename not in {
                        "manifest.json",
                        "records.json",
                    } and not info.filename.startswith("objects/sha256/"):
                        raise ProjectPortabilityError("project archive contains an unsafe entry")
                    if info.filename.startswith(("/", "\\")) or ".." in info.filename.split("/"):
                        raise ProjectPortabilityError("project archive contains an unsafe path")
                    total += info.file_size
                    if total > self._max_export_bytes:
                        raise ProjectPortabilityError(
                            "expanded project archive exceeds the size limit"
                        )
                    if info.file_size > 1024 * 1024 and info.compress_size * 200 < info.file_size:
                        raise ProjectPortabilityError(
                            "project archive has a suspicious compression ratio"
                        )
                manifest = json.loads(archive.read("manifest.json"))
                records = json.loads(archive.read("records.json"))
                if not isinstance(manifest, dict) or not isinstance(records, dict):
                    raise ProjectPortabilityError("project archive metadata is invalid")
                if manifest.get("schema_version") != "gamecrafter-portable-project-v2":
                    raise ProjectPortabilityError("unsupported project archive version")
                objects = manifest.get("objects")
                if not isinstance(objects, list):
                    raise ProjectPortabilityError("project archive object manifest is invalid")
                object_payloads: dict[str, bytes] = {}
                object_ids: set[str] = set()
                expected_names = {"manifest.json", "records.json"}
                for item in objects:
                    if not isinstance(item, dict):
                        raise ProjectPortabilityError("project archive object metadata is invalid")
                    key = str(item.get("object_key", ""))
                    digest = str(item.get("sha256", ""))
                    object_id = str(item.get("id", ""))
                    name = f"objects/{key}"
                    expected_names.add(name)
                    if (
                        name not in names
                        or re.fullmatch(r"sha256/[0-9a-f]{2}/[0-9a-f]{64}", key) is None
                        or key != f"sha256/{digest[:2]}/{digest}"
                        or item.get("storage_backend") != "filesystem"
                        or not item.get("media_type")
                        or not item.get("created_at")
                        or object_id in object_ids
                        or key in object_payloads
                    ):
                        raise ProjectPortabilityError(
                            "project archive contains invalid or duplicate object metadata"
                        )
                    self._uuid(object_id, "stored object id")
                    object_ids.add(object_id)
                    content = archive.read(name)
                    if (
                        len(content) != item.get("size_bytes")
                        or hashlib.sha256(content).hexdigest() != digest
                    ):
                        raise ProjectPortabilityError(
                            "project archive object failed integrity verification"
                        )
                    object_payloads[key] = content
                if set(names) != expected_names:
                    raise ProjectPortabilityError("project archive contains undeclared objects")
                return manifest, records, object_payloads
        except (
            BadZipFile,
            binascii.Error,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ProjectPortabilityError("project archive is invalid or corrupted") from error

    @staticmethod
    def _project_descendant_table_names() -> set[str]:
        names = {ProjectRecord.__table__.name}
        changed = True
        while changed:
            changed = False
            for table in Base.metadata.sorted_tables:
                if table.name in names or table.name == StoredObjectRecord.__table__.name:
                    continue
                if any(
                    foreign_key.column.table.name in names for foreign_key in table.foreign_keys
                ):
                    names.add(table.name)
                    changed = True
        return names

    @staticmethod
    def _database_row(table, item: dict[str, Any]) -> dict[str, Any]:
        unknown = set(item) - set(table.c.keys())
        if unknown:
            raise ProjectPortabilityError(f"archive table {table.name} contains unknown columns")
        result: dict[str, Any] = {}
        for column in table.c:
            if column.name not in item:
                continue
            value = item[column.name]
            if value is not None and isinstance(column.type, Uuid):
                value = DatabaseProjectPortabilityService._uuid(value, column.name)
            elif value is not None and isinstance(column.type, DateTime):
                value = datetime.fromisoformat(str(value))
            elif value is not None and isinstance(column.type, Date):
                value = date.fromisoformat(str(value))
            elif value is not None and isinstance(column.type, LargeBinary):
                if not isinstance(value, dict) or set(value) != {"base64"}:
                    raise ProjectPortabilityError("archive contains invalid binary data")
                value = base64.b64decode(value["base64"], validate=True)
            result[column.name] = value
        return result

    @staticmethod
    def _uuid(value: Any, label: str) -> UUID:
        try:
            return UUID(str(value))
        except (TypeError, ValueError) as error:
            raise ProjectPortabilityError(f"archive contains an invalid {label}") from error

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
