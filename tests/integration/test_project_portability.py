import json
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gamecrafter.infrastructure.database.local_source_service import DatabaseLocalSourceService
from gamecrafter.infrastructure.database.models import Base, ProjectRecord
from gamecrafter.infrastructure.database.project_portability import (
    DatabaseProjectPortabilityService,
    ProjectPortabilityError,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService
from gamecrafter.infrastructure.storage.local import LocalObjectStorage


def test_portable_export_contains_private_objects_and_typed_delete_removes_project(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    project_id = DatabaseRunService(sessions).create_project(slug="portable", name="Portable")
    storage = LocalObjectStorage(tmp_path / "objects")
    local = DatabaseLocalSourceService(sessions, storage, max_bytes=1024 * 1024)
    local.import_text(
        project_id=project_id,
        document_key="private-notes",
        kind="document",
        title="Private notes",
        filename="notes.md",
        content="# Private\nOwned content",
        media_type="text/markdown",
        locale="en",
        region="private",
        actor_id="owner",
        command_key="portable-source-1",
    )
    service = DatabaseProjectPortabilityService(sessions, storage)
    filename, payload = service.export_zip(project_id)
    assert filename == "gamecrafter-portable.zip"
    with ZipFile(BytesIO(payload)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        records = json.loads(archive.read("records.json"))
        assert manifest["schema_version"] == "gamecrafter-portable-project-v2"
        assert manifest["objects"][0]["id"]
        assert manifest["contains_private_material"] is True
        assert records["projects"][0]["id"] == str(project_id)
        # Raw and normalized payloads are content-addressed and deduplicate when identical.
        assert len([name for name in archive.namelist() if name.startswith("objects/")]) == 1
    with pytest.raises(ProjectPortabilityError, match="DELETE portable"):
        service.delete_project(project_id=project_id, confirmation="portable")
    result = service.delete_project(project_id=project_id, confirmation="DELETE portable")
    assert result["deleted"] is True and result["removed_unreferenced_objects"] == 1
    with sessions() as session:
        assert session.get(ProjectRecord, UUID(str(project_id))) is None
    restored = service.restore_zip(payload)
    assert restored["project_id"] == str(project_id)
    assert restored["object_count"] == 1
    with sessions() as session:
        assert session.get(ProjectRecord, UUID(str(project_id))).slug == "portable"
    with pytest.raises(ProjectPortabilityError, match="already exists"):
        service.restore_zip(payload)


def test_restore_rejects_corrupted_and_undeclared_archive_entries(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    project_id = DatabaseRunService(sessions).create_project(slug="safe", name="Safe")
    service = DatabaseProjectPortabilityService(sessions, LocalObjectStorage(tmp_path / "objects"))
    _, payload = service.export_zip(project_id)
    service.delete_project(project_id=project_id, confirmation="DELETE safe")

    source = ZipFile(BytesIO(payload))
    target = BytesIO()
    with source, ZipFile(target, "w", ZIP_DEFLATED) as changed:
        for name in source.namelist():
            changed.writestr(name, source.read(name))
        changed.writestr("../outside.txt", b"unsafe")
    with pytest.raises(ProjectPortabilityError, match="unsafe"):
        service.restore_zip(target.getvalue())
    with sessions() as session:
        assert session.get(ProjectRecord, UUID(str(project_id))) is None
