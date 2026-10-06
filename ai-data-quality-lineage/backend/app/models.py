from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now(): return datetime.now(timezone.utc)

class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    version: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="processing")
    parent_version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    column_name: Mapped[str] = mapped_column(String(200))
    rule_type: Mapped[str] = mapped_column(String(50))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"))
    detector: Mapped[str] = mapped_column(String(80))
    field: Mapped[str | None] = mapped_column(String(200), nullable=True)
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(255))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Proposal(Base):
    __tablename__ = "correction_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"))
    finding_id: Mapped[int | None] = mapped_column(ForeignKey("findings.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    risk: Mapped[str] = mapped_column(String(20), default="high")
    status: Mapped[str] = mapped_column(String(30), default="pending_review")
    proposed_by: Mapped[str] = mapped_column(String(100), default="system")
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class LineageEdge(Base):
    __tablename__ = "lineage_edges"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(255))
    target: Mapped[str] = mapped_column(String(255))
    edge_type: Mapped[str] = mapped_column(String(50))
    transformation: Mapped[str] = mapped_column(Text, default="identity")
    version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id"), nullable=True)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(20))
    recipient: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="simulated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

