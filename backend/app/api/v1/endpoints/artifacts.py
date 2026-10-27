import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.artifact import (
    ArtifactCompareResponse, ArtifactDetail, ArtifactListResponse, ArtifactRestoreRequest,
    ArtifactSummary, ArtifactVersionCreate, ArtifactVersionDetail, ArtifactVersionListResponse,
)
from app.services.artifact_service import artifact_summary, get_artifact, list_artifacts
from app.services.artifact_version_service import compare_versions, get_version, list_versions, restore_version, save_version

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("", response_model=ArtifactListResponse)
def artifacts_list(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=200)] = None,
    artifact_type: Literal["document", "code", "research", "report"] | None = None,
    agent_id: Annotated[str | None, Query(max_length=50)] = None,
    task_id: Annotated[int | None, Query(gt=0)] = None,
    workflow_run_id: Annotated[int | None, Query(gt=0)] = None,
) -> ArtifactListResponse:
    return list_artifacts(db, limit=limit, offset=offset, search=search, artifact_type=artifact_type, agent_id=agent_id, task_id=task_id, workflow_run_id=workflow_run_id)


@router.get("/summary", response_model=ArtifactSummary)
def artifacts_summary(db: Annotated[Session, Depends(get_db)]) -> ArtifactSummary:
    return artifact_summary(db)


@router.get("/{artifact_id}", response_model=ArtifactDetail)
def artifact_detail(artifact_id: int, db: Annotated[Session, Depends(get_db)]) -> ArtifactDetail:
    return get_artifact(db, artifact_id)


@router.get("/{artifact_id}/download")
def artifact_download(artifact_id: int, db: Annotated[Session, Depends(get_db)]) -> Response:
    artifact = get_artifact(db, artifact_id)
    extension = {"plain_text": "txt", "markdown": "md", "json": "json", "code": "txt"}[artifact.content_format]
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", artifact.title).strip("-")[:80] or "artifact"
    filename = f"artifact-{artifact.id}-{stem}.{extension}"
    media_type = {"plain_text": "text/plain", "markdown": "text/markdown", "json": "application/json", "code": "text/plain"}[artifact.content_format]
    return Response(content=artifact.content.encode("utf-8"), media_type=f"{media_type}; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff"})


@router.get("/{artifact_id}/versions", response_model=ArtifactVersionListResponse)
def artifact_versions(
    artifact_id: int, db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ArtifactVersionListResponse:
    return list_versions(db, artifact_id, limit, offset)


@router.post("/{artifact_id}/versions", response_model=ArtifactVersionDetail)
def artifact_save_version(artifact_id: int, payload: ArtifactVersionCreate, db: Annotated[Session, Depends(get_db)]) -> ArtifactVersionDetail:
    return save_version(db, artifact_id, payload)


@router.get("/{artifact_id}/versions/{version_number}", response_model=ArtifactVersionDetail)
def artifact_version_detail(artifact_id: int, version_number: int, db: Annotated[Session, Depends(get_db)]) -> ArtifactVersionDetail:
    return get_version(db, artifact_id, version_number)


@router.get("/{artifact_id}/compare", response_model=ArtifactCompareResponse)
def artifact_compare(
    artifact_id: int, db: Annotated[Session, Depends(get_db)],
    from_version: Annotated[int, Query(ge=1)], to_version: Annotated[int, Query(ge=1)],
) -> ArtifactCompareResponse:
    return compare_versions(db, artifact_id, from_version, to_version)


@router.post("/{artifact_id}/restore", response_model=ArtifactVersionDetail)
def artifact_restore(artifact_id: int, payload: ArtifactRestoreRequest, db: Annotated[Session, Depends(get_db)]) -> ArtifactVersionDetail:
    return restore_version(db, artifact_id, payload)


@router.get("/{artifact_id}/versions/{version_number}/download")
def artifact_version_download(artifact_id: int, version_number: int, db: Annotated[Session, Depends(get_db)]) -> Response:
    version = get_version(db, artifact_id, version_number)
    extension = {"plain_text": "txt", "markdown": "md", "json": "json", "code": "txt"}[version.content_format]
    filename = f"artifact-{artifact_id}-version-{version_number}.{extension}"
    media_type = {"plain_text": "text/plain", "markdown": "text/markdown", "json": "application/json", "code": "text/plain"}[version.content_format]
    return Response(content=version.content.encode("utf-8"), media_type=f"{media_type}; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff"})
