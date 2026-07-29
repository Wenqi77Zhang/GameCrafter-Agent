from hashlib import sha256

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gamecrafter.domain.knowledge.sources import AssetRole, CaptureMethod, SourceType
from gamecrafter.infrastructure.database.models import (
    Base,
    ContentFamilyRecord,
    SourceAssetRecord,
    SourceRecord,
    SourceVersionRecord,
    StoredObjectRecord,
)
from gamecrafter.infrastructure.database.run_service import DatabaseRunService


def make_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_source_revision_references_deduplicated_stored_evidence() -> None:
    sessions = make_session_factory()
    project_id = DatabaseRunService(sessions).create_project(slug="nte-source", name="异环")
    raw_html = b"<main>NTE evidence</main>"
    raw_digest = sha256(raw_html).hexdigest()
    text_digest = sha256(b"NTE evidence").hexdigest()
    fingerprint = sha256(f"{raw_digest}:{text_digest}".encode()).hexdigest()

    with sessions.begin() as session:
        family = ContentFamilyRecord(
            project_id=project_id,
            family_key="launch-2026-04-29",
            label="NTE launch",
            source_type=SourceType.NEWS.value,
        )
        session.add(family)
        session.flush()
        source = SourceRecord(
            project_id=project_id,
            content_family_id=family.id,
            canonical_url="https://nte.perfectworld.com/en/example.html",
            site_key="nte-global",
            locale="en",
            region="global",
            source_type=SourceType.NEWS.value,
            raw_category="gamenews",
        )
        stored = StoredObjectRecord(
            object_key=f"sha256/{raw_digest[:2]}/{raw_digest}",
            sha256=raw_digest,
            size_bytes=len(raw_html),
            media_type="text/html",
        )
        session.add_all([source, stored])
        session.flush()
        version = SourceVersionRecord(
            source_id=source.id,
            version_number=1,
            title="NTE launch",
            capture_method=CaptureMethod.HTTP.value,
            change_kind="initial",
            raw_content_sha256=raw_digest,
            normalized_text_sha256=text_digest,
            evidence_fingerprint_sha256=fingerprint,
            parser_version="test-parser-v1",
            capture_policy_version="test-policy-v1",
        )
        session.add(version)
        session.flush()
        session.add(
            SourceAssetRecord(
                source_version_id=version.id,
                stored_object_id=stored.id,
                role=AssetRole.RAW_HTML.value,
                ordinal=0,
            )
        )

    with sessions() as session:
        source = session.scalar(select(SourceRecord).where(SourceRecord.project_id == project_id))
        version = session.scalar(
            select(SourceVersionRecord).where(SourceVersionRecord.source_id == source.id)
        )
        asset = session.scalar(
            select(SourceAssetRecord).where(SourceAssetRecord.source_version_id == version.id)
        )
        stored = session.get(StoredObjectRecord, asset.stored_object_id)

    assert source is not None
    assert source.content_family_id is not None
    assert version is not None
    assert version.version_number == 1
    assert asset is not None
    assert stored is not None
    assert stored.sha256 == raw_digest
