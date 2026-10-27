import difflib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.models.artifact import Artifact
from app.models.artifact_version import ArtifactVersion
from app.schemas.artifact import (
    ArtifactCompareResponse, ArtifactRestoreRequest, ArtifactVersionCreate,
    ArtifactVersionDetail, ArtifactVersionListItem, ArtifactVersionListResponse,
)

MAX_COMPARE_CHARS = 200_000
MAX_DIFF_CHARS = 500_000


def _artifact(db: Session, artifact_id: int, *, lock: bool = False) -> Artifact:
    statement = select(Artifact).where(Artifact.id == artifact_id)
    if lock: statement = statement.with_for_update()
    artifact = db.scalar(statement)
    if artifact is None: raise ApplicationError(404, "ARTIFACT_NOT_FOUND", f"Artifact {artifact_id} not found.")
    return artifact


def _version(db: Session, artifact_id: int, version_number: int) -> ArtifactVersion:
    version = db.scalar(select(ArtifactVersion).where(
        ArtifactVersion.artifact_id == artifact_id, ArtifactVersion.version_number == version_number,
    ))
    if version is None: raise ApplicationError(404, "ARTIFACT_VERSION_NOT_FOUND", f"Version {version_number} was not found.")
    return version


def _item(db: Session, version: ArtifactVersion) -> ArtifactVersionListItem:
    restored_number = None
    if version.restored_from_version_id is not None:
        restored_number = db.scalar(select(ArtifactVersion.version_number).where(
            ArtifactVersion.id == version.restored_from_version_id,
            ArtifactVersion.artifact_id == version.artifact_id,
        ))
    return ArtifactVersionListItem(
        id=version.id, version_number=version.version_number, source=version.source,
        change_summary=version.change_summary, restored_from_version_id=version.restored_from_version_id,
        restored_from_version_number=restored_number, created_at=version.created_at,
        content_size=len(version.content),
    )


def _detail(db: Session, version: ArtifactVersion) -> ArtifactVersionDetail:
    return ArtifactVersionDetail(
        **_item(db, version).model_dump(), artifact_id=version.artifact_id, content=version.content,
        content_format=version.content_format, language=version.language,
    )


def save_version(db: Session, artifact_id: int, payload: ArtifactVersionCreate) -> ArtifactVersionDetail:
    artifact = _artifact(db, artifact_id, lock=True)
    if artifact.current_version_number != payload.expected_version_number:
        db.rollback()
        raise ApplicationError(409, "ARTIFACT_VERSION_CONFLICT", "Artifact changed since editing began. Reload the latest version before saving.")
    current = _version(db, artifact_id, artifact.current_version_number)
    language = payload.language if payload.content_format == "code" else None
    if current.content == payload.content and current.content_format == payload.content_format and current.language == language:
        detail = _detail(db, current)
        db.rollback()
        return detail
    next_number = artifact.current_version_number + 1
    version = ArtifactVersion(
        artifact_id=artifact.id, version_number=next_number, content=payload.content,
        content_format=payload.content_format, language=language, change_summary=payload.change_summary,
        source="user",
    )
    artifact.content = payload.content; artifact.content_format = payload.content_format
    artifact.language = language; artifact.current_version_number = next_number
    try:
        db.add(version); db.commit(); db.refresh(version); return _detail(db, version)
    except Exception:
        db.rollback(); raise


def restore_version(db: Session, artifact_id: int, payload: ArtifactRestoreRequest) -> ArtifactVersionDetail:
    artifact = _artifact(db, artifact_id, lock=True)
    if artifact.current_version_number != payload.expected_version_number:
        db.rollback()
        raise ApplicationError(409, "ARTIFACT_VERSION_CONFLICT", "Artifact changed before restore. Reload the latest version.")
    source_version = _version(db, artifact_id, payload.version_number)
    next_number = artifact.current_version_number + 1
    version = ArtifactVersion(
        artifact_id=artifact.id, version_number=next_number, content=source_version.content,
        content_format=source_version.content_format, language=source_version.language,
        source="restore", restored_from_version_id=source_version.id,
        change_summary=f"Restored from version {source_version.version_number}.",
    )
    artifact.content = source_version.content; artifact.content_format = source_version.content_format
    artifact.language = source_version.language; artifact.current_version_number = next_number
    try:
        db.add(version); db.commit(); db.refresh(version); return _detail(db, version)
    except Exception:
        db.rollback(); raise


def list_versions(db: Session, artifact_id: int, limit: int, offset: int) -> ArtifactVersionListResponse:
    artifact = _artifact(db, artifact_id)
    total = db.scalar(select(func.count(ArtifactVersion.id)).where(ArtifactVersion.artifact_id == artifact_id)) or 0
    versions = db.scalars(select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact_id).order_by(
        ArtifactVersion.version_number.desc(), ArtifactVersion.id.desc()
    ).offset(offset).limit(limit)).all()
    return ArtifactVersionListResponse(items=[_item(db, item) for item in versions], total=total, limit=limit, offset=offset, current_version_number=artifact.current_version_number)


def get_version(db: Session, artifact_id: int, version_number: int) -> ArtifactVersionDetail:
    _artifact(db, artifact_id)
    return _detail(db, _version(db, artifact_id, version_number))


def compare_versions(db: Session, artifact_id: int, from_version: int, to_version: int) -> ArtifactCompareResponse:
    first = _version(db, artifact_id, from_version); second = _version(db, artifact_id, to_version)
    if len(first.content) > MAX_COMPARE_CHARS or len(second.content) > MAX_COMPARE_CHARS:
        raise ApplicationError(413, "ARTIFACT_COMPARE_TOO_LARGE", f"Version comparison is limited to {MAX_COMPARE_CHARS:,} characters per version.")
    lines = list(difflib.unified_diff(first.content.splitlines(), second.content.splitlines(), fromfile=f"version-{from_version}", tofile=f"version-{to_version}", lineterm=""))
    diff = "\n".join(lines)
    if len(diff) > MAX_DIFF_CHARS:
        raise ApplicationError(413, "ARTIFACT_DIFF_TOO_LARGE", "Generated diff exceeds the 500,000 character response limit.")
    added = sum(line.startswith("+") and not line.startswith("+++") for line in lines)
    removed = sum(line.startswith("-") and not line.startswith("---") for line in lines)
    return ArtifactCompareResponse(artifact_id=artifact_id, from_version=from_version, to_version=to_version, unified_diff=diff, added_lines=added, removed_lines=removed)


def backfill_artifact_versions(db: Session, artifact_ids: set[int] | None = None) -> int:
    statement = select(Artifact).outerjoin(
        ArtifactVersion,
        (ArtifactVersion.artifact_id == Artifact.id) & (ArtifactVersion.version_number == 1),
    ).where(ArtifactVersion.id.is_(None))
    if artifact_ids is not None: statement = statement.where(Artifact.id.in_(artifact_ids))
    artifacts = db.scalars(statement).all()
    for artifact in artifacts:
        artifact.current_version_number = 1
        db.add(ArtifactVersion(
            artifact_id=artifact.id, version_number=1, content=artifact.content,
            content_format=artifact.content_format, language=artifact.language, source="backfill",
            change_summary="Original version backfilled from the existing artifact.",
        ))
    db.flush()
    return len(artifacts)
