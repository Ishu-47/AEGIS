import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
    Float,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )
    api_key_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
    )


class LogEvent(Base):
    __tablename__ = "log_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    service: Mapped[str] = mapped_column(String(150), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True,
    )
    raw_event: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    fingerprint: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    service: Mapped[str] = mapped_column(String(150), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="open",
        nullable=False,
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    event_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    application: Mapped["Application"] = relationship(
        back_populates="incidents",
    )
    report: Mapped["InvestigationReport | None"] = relationship(
        back_populates="incident",
        uselist=False,
        cascade="all, delete-orphan",
    )


class IncidentEvent(Base):
    __tablename__ = "incident_events"

    __table_args__ = (UniqueConstraint(
        "incident_id", "log_event_id", name="uq_incident_log_event",
    ),)

    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    log_event_id: Mapped[int] = mapped_column(
        ForeignKey("log_events.id", ondelete="CASCADE"),
        primary_key=True,
    )


class InvestigationReport(Base):
    """Stores the structured output of the AI investigation pipeline."""
    __tablename__ = "investigation_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    observed_error: Mapped[str] = mapped_column(Text, nullable=False)
    affected_service: Mapped[str] = mapped_column(String(150), nullable=False)
    probable_root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )
    remediation_steps: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )
    stack_trace_locations: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )
    confidence: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
    )
    uncertainty_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    raw_llm_response: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    incident: Mapped["Incident"] = relationship(
        back_populates="report",
    )
