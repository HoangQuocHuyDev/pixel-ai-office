"""Explicit, idempotent artifact backfill. Run manually after reviewing the target database."""
from app.db.session import SessionLocal
from app.services.artifact_service import backfill_artifacts
from app.services.artifact_version_service import backfill_artifact_versions


if __name__ == "__main__":
    with SessionLocal() as session:
        executions, reports = backfill_artifacts(session)
        versions = backfill_artifact_versions(session)
        session.commit()
    print(f"Created {executions} execution artifacts, {reports} report artifacts, and {versions} missing original versions.")
