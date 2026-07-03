from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RunCreateInput(BaseModel):
    area: str = Field(min_length=2, max_length=160)
    notes: str = Field(default="", max_length=2_000)
    idempotency_key: str | None = Field(default=None, max_length=120)


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    title: str
    source_uri: str
    citation: str
    excerpt: str
    knowledge_asset_id: int | None = None
    artifact_id: int | None = None
    task_id: int | None = None


class AgentOutputRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    title: str
    output_type: str
    content: str
    safety_flags: list[str]
    created_at: datetime


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    artifact_type: str
    title: str
    content: str
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    agent_name: str
    status: str
    attempt_count: int
    max_attempts: int
    last_error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    depends_on_task_ids: list[int]


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    area: str
    notes: str
    status: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    tasks: list[TaskRead]
    outputs: list[AgentOutputRead]
    artifacts: list[ArtifactRead]
    evidence: list[EvidenceRead]


class KnowledgeAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    source_path: str
    summary: str


class RunComparisonRead(BaseModel):
    left_run_id: str
    right_run_id: str
    left_status: str
    right_status: str
    left_artifacts: list[str]
    right_artifacts: list[str]
    left_task_counts: dict[str, int]
    right_task_counts: dict[str, int]
