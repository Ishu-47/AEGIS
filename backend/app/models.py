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
from sqlalchemy.types import UserDefinedType

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # Allows non-RAG API/test use without the optional driver package.
    class Vector(UserDefinedType):
        cache_ok = True
        def __init__(self, dimensions: int): self.dimensions = dimensions
        def get_col_spec(self, **kwargs): return f"VECTOR({self.dimensions})"
        def bind_processor(self, dialect):
            def process(value):
                return None if value is None else "[" + ",".join(str(float(x)) for x in value) + "]"
            return process

from app.database import Base


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

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
    platform: Mapped[str] = mapped_column(String(50), default="Other", nullable=False)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
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
    knowledge_documents: Mapped[list["KnowledgeDocument"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
    )




# ---------------------------------------------------------------------------
# Dashboard accounts and server-side sessions
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


# ---------------------------------------------------------------------------
# Log Event
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Incident
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Incident ↔ Event junction
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Investigation Report  (enhanced — 11-section evidence-backed reports)
# ---------------------------------------------------------------------------

class InvestigationReport(Base):
    """Stores the structured output of the AI investigation pipeline.

    Every field maps to one of the 11 required report sections:
      1. incident_summary       — Executive incident overview
      2. observed_error         — What error was observed
      3. affected_service       — Primary service affected
      4. downstream_services    — Services impacted downstream
      5. timeline_summary       — Chronological reconstruction with event refs
      6. probable_root_cause    — Most likely root cause
      7. alternative_hypotheses — Other possible explanations, ranked
      8. supporting_evidence    — Evidence items citing event IDs / timestamps
      9. confidence + factors   — Calibrated confidence with breakdown
     10. remediation_steps      — Recommended fixes
     11. verification_steps     — Steps to confirm resolution
    """
    __tablename__ = "investigation_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # 1 — Incident summary
    incident_summary: Mapped[str] = mapped_column(
        Text, default="", nullable=False,
    )

    # 2 — Observed error
    observed_error: Mapped[str] = mapped_column(Text, nullable=False)

    # 3 — Primary affected service
    affected_service: Mapped[str] = mapped_column(
        String(150), nullable=False,
    )

    # 4 — Downstream affected services
    downstream_services: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )

    # 5 — Chronological timeline with event references
    #      Each entry: {event_id, timestamp, severity, service, message}
    timeline_summary: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )

    # 6 — Probable root cause
    probable_root_cause: Mapped[str] = mapped_column(Text, nullable=False)

    # 7 — Alternative hypotheses
    #      Each entry: {hypothesis, probability, supporting_event_ids, reasoning}
    alternative_hypotheses: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )

    # 8 — Supporting evidence with actual event citations
    #      Each entry: text referencing specific event_id / timestamp
    supporting_evidence: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )

    # Evidence-to-claim mapping  {claim: [event_ids that support it]}
    evidence_mapping: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )

    # Stack trace locations extracted from events
    stack_trace_locations: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )

    # 9 — Confidence & calibration
    confidence: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
    )
    confidence_factors: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    uncertainty_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    # 10 — Remediation steps
    remediation_steps: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )

    # 11 — Verification steps
    verification_steps: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )

    # Investigation metadata
    raw_llm_response: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    investigation_steps: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )
    events_analyzed: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    events_cited: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    model_used: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    incident: Mapped["Incident"] = relationship(
        back_populates="report",
    )


# ---------------------------------------------------------------------------
# Knowledge Document  (RAG knowledge base — runbooks, post-mortems, SOPs)
# ---------------------------------------------------------------------------

class KnowledgeDocument(Base):
    """Stores runbooks, post-mortem reports, architecture docs, and SOPs
    that the investigation engine retrieves via RAG to enrich analysis."""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )  # runbook | postmortem | architecture | sop
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Embedding vector stored as JSON list of floats.
    # In production, replace with pgvector Vector(768) column for efficient
    # approximate nearest-neighbour search.
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    application: Mapped["Application"] = relationship(
        back_populates="knowledge_documents",
    )




# ---------------------------------------------------------------------------
# Persistent pgvector knowledge chunks
# ---------------------------------------------------------------------------

class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="runbook", nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    embedding: Mapped[list] = mapped_column(Vector(768), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


# ---------------------------------------------------------------------------
# Evaluation Case  (investigation quality measurement)
# ---------------------------------------------------------------------------

class EvaluationCase(Base):
    """Known-answer test cases for measuring investigation accuracy.

    Each case captures a set of events, the expected root cause, and the
    expected affected services so automated evaluation can score the
    investigation engine's output."""

    __tablename__ = "evaluation_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Input: events to feed into the investigation
    events_json: Mapped[list] = mapped_column(JSON, nullable=False)

    # Expected output
    expected_root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    expected_services: Mapped[list] = mapped_column(JSON, nullable=False)
    expected_severity: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )

    # Last evaluation result
    last_score: Mapped[float | None] = mapped_column(
        Float, nullable=True,
    )
    last_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
