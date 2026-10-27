from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ArtifactType = Literal["document", "code", "research", "report"]
ContentFormat = Literal["plain_text", "markdown", "json", "code"]


class ArtifactListItem(BaseModel):
    id: int
    title: str
    artifact_type: ArtifactType
    content_format: ContentFormat
    language: str | None
    agent_id: str | None
    agent_name: str | None
    task_id: int | None
    task_title: str | None
    workflow_run_id: int | None
    workflow_title: str | None
    created_at: datetime
    preview: str
    content_size: int
    current_version_number: int


class ArtifactListResponse(BaseModel):
    items: list[ArtifactListItem]
    total: int
    limit: int
    offset: int


class ArtifactDetail(ArtifactListItem):
    task_execution_id: int | None
    content: str
    updated_at: datetime


class ArtifactSummary(BaseModel):
    total_artifacts: int
    documents: int
    code: int
    research: int
    reports: int


class ArtifactVersionCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1_000_000)
    content_format: ContentFormat
    language: str | None = Field(default=None, max_length=50)
    change_summary: str | None = Field(default=None, max_length=500)
    expected_version_number: int = Field(ge=1)
    model_config = ConfigDict(extra="forbid")

    @field_validator("content")
    @classmethod
    def non_blank_content(cls, value: str) -> str:
        if not value.strip(): raise ValueError("Content cannot be blank.")
        return value

    @field_validator("language", "change_summary")
    @classmethod
    def trim_optional(cls, value: str | None) -> str | None:
        if value is None: return None
        return value.strip() or None


class ArtifactRestoreRequest(BaseModel):
    version_number: int = Field(ge=1)
    expected_version_number: int = Field(ge=1)
    model_config = ConfigDict(extra="forbid")


class ArtifactVersionListItem(BaseModel):
    id: int
    version_number: int
    source: Literal["agent", "user", "restore", "backfill"]
    change_summary: str | None
    restored_from_version_id: int | None
    restored_from_version_number: int | None = None
    created_at: datetime
    content_size: int


class ArtifactVersionDetail(ArtifactVersionListItem):
    artifact_id: int
    content: str
    content_format: ContentFormat
    language: str | None


class ArtifactVersionListResponse(BaseModel):
    items: list[ArtifactVersionListItem]
    total: int
    limit: int
    offset: int
    current_version_number: int


class ArtifactCompareResponse(BaseModel):
    artifact_id: int
    from_version: int
    to_version: int
    unified_diff: str
    added_lines: int
    removed_lines: int
