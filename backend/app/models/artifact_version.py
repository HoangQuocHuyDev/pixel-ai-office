from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Identity, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        CheckConstraint("version_number >= 1", name="check_artifact_version_number"),
        CheckConstraint("source IN ('agent', 'user', 'restore', 'backfill')", name="check_artifact_version_source"),
        CheckConstraint("content_format IN ('plain_text', 'markdown', 'json', 'code')", name="check_artifact_version_format"),
        CheckConstraint("char_length(content) BETWEEN 1 AND 1000000", name="check_artifact_version_content_size"),
        UniqueConstraint("artifact_id", "version_number", name="uq_artifact_versions_number"),
        UniqueConstraint("artifact_id", "id", name="uq_artifact_versions_artifact_id_id"),
        ForeignKeyConstraint(
            ["artifact_id", "restored_from_version_id"],
            ["artifact_versions.artifact_id", "artifact_versions.id"],
            name="fk_artifact_version_restore_same_artifact",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    artifact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_format: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    change_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    restored_from_version_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now())
