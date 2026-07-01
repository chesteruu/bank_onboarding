from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class SegmentStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FlowSegment(BaseModel):
    id: UUID | None = None
    application_id: UUID
    segment_key: str
    orchestrator_id: str
    component_flow_id: str
    status: SegmentStatus = SegmentStatus.PENDING
    internal_step_key: str | None = None
    internal_total_steps: int = 1
    percent: int = 0
    sequence: int = 0
    updated_at: datetime | None = None


class SegmentProgress(BaseModel):
    segment_key: str
    orchestrator_id: str
    status: SegmentStatus
    internal_step_key: str | None = None
    internal_step_title: str | None = None
    percent: int = 0


class AggregateProgress(BaseModel):
    main_percent: int = 0
    percent: int = 0
    current_step: int = 1
    total_steps: int = 1
    current_step_key: str = ""
    current_step_title: str = ""
    active_segment: SegmentProgress | None = None
    ready: bool = True
