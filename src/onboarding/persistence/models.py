from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class OnboardingApplicationORM(Base):
    __tablename__ = "onboarding_applications"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    country: Mapped[str] = mapped_column(String(2))
    account_type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    current_step_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    identifier_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    step_submissions: Mapped[list["StepSubmissionORM"]] = relationship(back_populates="application")
    integration_results: Mapped[list["IntegrationResultORM"]] = relationship(
        back_populates="application"
    )
    audit_events: Mapped[list["AuditEventORM"]] = relationship(back_populates="application")


class StepSubmissionORM(Base):
    __tablename__ = "step_submissions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("onboarding_applications.id"), index=True
    )
    step_key: Mapped[str] = mapped_column(String(64))
    answers_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    application: Mapped[OnboardingApplicationORM] = relationship(back_populates="step_submissions")


class IntegrationResultORM(Base):
    __tablename__ = "integration_results"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("onboarding_applications.id"), index=True
    )
    check_type: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(64))
    request_payload_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    outcome: Mapped[str] = mapped_column(String(32))
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    application: Mapped[OnboardingApplicationORM] = relationship(
        back_populates="integration_results"
    )


class AuditEventORM(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("onboarding_applications.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64), default="system")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped[OnboardingApplicationORM] = relationship(back_populates="audit_events")


class ResumeTokenORM(Base):
    """Single-use resume tokens with a 24-hour TTL."""

    __tablename__ = "resume_tokens"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("onboarding_applications.id"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    resumption_data_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FlowTraceORM(Base):
    __tablename__ = "flow_trace"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("onboarding_applications.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64), default="system")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntegrationTraceORM(Base):
    __tablename__ = "integration_trace"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("onboarding_applications.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64), default="system")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DecisionTraceORM(Base):
    __tablename__ = "decision_trace"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("onboarding_applications.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64), default="system")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventOutboxORM(Base):
    __tablename__ = "event_outbox"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(128))
    routing_key: Mapped[str] = mapped_column(String(256))
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(default=0)


class FlowSegmentORM(Base):
    __tablename__ = "flow_segments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("onboarding_applications.id"), index=True
    )
    segment_key: Mapped[str] = mapped_column(String(64))
    orchestrator_id: Mapped[str] = mapped_column(String(64))
    component_flow_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    internal_step_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    internal_total_steps: Mapped[int] = mapped_column(default=1)
    percent: Mapped[int] = mapped_column(default=0)
    sequence: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
