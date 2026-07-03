from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    blocked = "blocked"
    failed = "failed"


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    area: Mapped[str] = mapped_column(String(160), index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.queued.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tasks: Mapped[list["Task"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    outputs: Mapped[list["AgentOutput"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("task_key", name="uq_task_task_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(160))
    agent_name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.queued.value, index=True)
    task_key: Mapped[str] = mapped_column(String(160))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped["Run"] = relationship(back_populates="tasks")
    outputs: Mapped[list["AgentOutput"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    dependencies: Mapped[list["TaskDependency"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        foreign_keys="TaskDependency.task_id",
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    depends_on_task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)

    task: Mapped["Task"] = relationship(back_populates="dependencies", foreign_keys=[task_id])


class AgentOutput(Base):
    __tablename__ = "agent_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    output_type: Mapped[str] = mapped_column(String(60), index=True)
    content: Mapped[str] = mapped_column(Text)
    safety_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped["Run"] = relationship(back_populates="outputs")
    task: Mapped["Task"] = relationship(back_populates="outputs")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped["Run"] = relationship(back_populates="artifacts")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="artifact")


class KnowledgeAsset(Base):
    __tablename__ = "knowledge_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    source_path: Mapped[str] = mapped_column(String(255), unique=True)
    body: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="knowledge_asset")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    artifact_id: Mapped[int | None] = mapped_column(ForeignKey("artifacts.id"), nullable=True, index=True)
    knowledge_asset_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_assets.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    source_uri: Mapped[str] = mapped_column(String(255))
    citation: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped["Run"] = relationship(back_populates="evidence")
    task: Mapped["Task"] = relationship(back_populates="evidence")
    artifact: Mapped["Artifact"] = relationship(back_populates="evidence")
    knowledge_asset: Mapped["KnowledgeAsset"] = relationship(back_populates="evidence")
