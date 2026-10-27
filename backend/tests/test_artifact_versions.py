from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, func, select

from app.core.exceptions import ApplicationError
from app.db.session import SessionLocal
from app.main import app
from app.models.artifact import Artifact
from app.models.artifact_version import ArtifactVersion
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.schemas.artifact import ArtifactRestoreRequest, ArtifactVersionCreate
from app.services.artifact_service import create_execution_artifact
from app.services.artifact_version_service import backfill_artifact_versions, compare_versions, get_version, list_versions, restore_version, save_version


def seed_artifact(*, with_version: bool = True) -> tuple[int, int, int]:
    with SessionLocal() as db:
        task = Task(title="Versioned artifact", status="done", priority="medium", assigned_agent_id="developer", completed_at=datetime.now(timezone.utc))
        db.add(task); db.flush()
        execution = TaskExecution(task_id=task.id, agent_id="developer", status="completed", input_snapshot="private", output_content="line one\nline two", completed_at=datetime.now(timezone.utc))
        db.add(execution); db.flush()
        if with_version:
            artifact = create_execution_artifact(db, execution, task)
        else:
            artifact = Artifact(title="Legacy", artifact_type="document", content="legacy content", content_format="plain_text", agent_id="developer", task_id=task.id, task_execution_id=execution.id)
            db.add(artifact); db.flush()
        assert artifact is not None
        db.commit(); return task.id, execution.id, artifact.id


def cleanup(task_id: int) -> None:
    with SessionLocal() as db: db.execute(delete(Task).where(Task.id == task_id)); db.commit()


def test_new_artifact_has_immutable_original_and_backfill_is_idempotent() -> None:
    task_id, _, artifact_id = seed_artifact()
    try:
        with SessionLocal() as db:
            original = get_version(db, artifact_id, 1)
            assert original.source == "agent" and original.content == "line one\nline two"
            assert backfill_artifact_versions(db, {artifact_id}) == 0
    finally: cleanup(task_id)

    task_id, _, artifact_id = seed_artifact(with_version=False)
    try:
        with SessionLocal() as db:
            assert backfill_artifact_versions(db, {artifact_id}) == 1; db.commit()
            assert backfill_artifact_versions(db, {artifact_id}) == 0
            assert get_version(db, artifact_id, 1).source == "backfill"
    finally: cleanup(task_id)


def test_save_compare_restore_and_history_pagination() -> None:
    task_id, _, artifact_id = seed_artifact()
    try:
        with SessionLocal() as db:
            saved = save_version(db, artifact_id, ArtifactVersionCreate(content="line one\nline changed\nline added", content_format="plain_text", change_summary="Revise text", expected_version_number=1))
            assert saved.version_number == 2 and saved.source == "user"
        with SessionLocal() as db:
            original = get_version(db, artifact_id, 1)
            assert original.content == "line one\nline two"
            comparison = compare_versions(db, artifact_id, 1, 2)
            assert comparison.added_lines == 2 and comparison.removed_lines == 1
            restored = restore_version(db, artifact_id, ArtifactRestoreRequest(version_number=1, expected_version_number=2))
            assert restored.version_number == 3 and restored.source == "restore" and restored.restored_from_version_number == 1
        with SessionLocal() as db:
            history = list_versions(db, artifact_id, 2, 0); page_two = list_versions(db, artifact_id, 2, 2)
            artifact = db.get(Artifact, artifact_id)
            assert history.total == 3 and [v.version_number for v in history.items] == [3, 2]
            assert [v.version_number for v in page_two.items] == [1]
            assert artifact and artifact.content == original.content and artifact.current_version_number == 3
    finally: cleanup(task_id)


def test_optimistic_conflict_noop_and_size_validation() -> None:
    task_id, _, artifact_id = seed_artifact()
    try:
        payload = ArtifactVersionCreate(content="updated", content_format="plain_text", expected_version_number=1)
        with SessionLocal() as first: assert save_version(first, artifact_id, payload).version_number == 2
        with SessionLocal() as stale, pytest.raises(ApplicationError) as conflict: save_version(stale, artifact_id, payload)
        assert conflict.value.status_code == 409
        with SessionLocal() as db:
            count_before = db.scalar(select(func.count(ArtifactVersion.id)).where(ArtifactVersion.artifact_id == artifact_id))
            same = save_version(db, artifact_id, ArtifactVersionCreate(content="updated", content_format="plain_text", expected_version_number=2))
            count_after = db.scalar(select(func.count(ArtifactVersion.id)).where(ArtifactVersion.artifact_id == artifact_id))
            assert same.version_number == 2 and count_before == count_after
        with pytest.raises(ValidationError): ArtifactVersionCreate(content="x" * 1_000_001, content_format="plain_text", expected_version_number=2)
    finally: cleanup(task_id)


def test_version_api_and_historical_download_do_not_expose_prompt() -> None:
    task_id, _, artifact_id = seed_artifact()
    try:
        with TestClient(app) as client:
            saved = client.post(f"/api/v1/artifacts/{artifact_id}/versions", json={"content": "API edit", "content_format": "plain_text", "language": None, "change_summary": "API", "expected_version_number": 1})
            history = client.get(f"/api/v1/artifacts/{artifact_id}/versions", params={"limit": 1, "offset": 0})
            detail = client.get(f"/api/v1/artifacts/{artifact_id}/versions/1")
            download = client.get(f"/api/v1/artifacts/{artifact_id}/versions/1/download")
            missing = client.get(f"/api/v1/artifacts/{artifact_id}/versions/99")
        assert saved.status_code == 200 and saved.json()["version_number"] == 2
        assert history.json()["total"] == 2 and "content" not in history.json()["items"][0]
        assert detail.json()["content"] == "line one\nline two" and "private" not in detail.text
        assert download.status_code == 200 and "attachment" in download.headers["content-disposition"]
        assert download.headers["x-content-type-options"] == "nosniff"
        assert missing.status_code == 404
    finally: cleanup(task_id)
