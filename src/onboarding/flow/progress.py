from __future__ import annotations

from onboarding.domain.events.segment import (
    AggregateProgress,
    FlowSegment,
    SegmentProgress,
    SegmentStatus,
)
from onboarding.domain.models import Application, FlowDefinition


def compute_aggregate_progress(
    app: Application,
    flow: FlowDefinition,
    segments: list[FlowSegment],
) -> AggregateProgress:
    keys = flow.step_keys()
    total = len(keys) or 1
    current_key = app.current_step_key or keys[0]
    try:
        idx = keys.index(current_key)
    except ValueError:
        idx = 0

    completed_before = idx
    active = next(
        (
            s
            for s in segments
            if s.segment_key == current_key
            and s.status in (SegmentStatus.ACTIVE, SegmentStatus.PROCESSING)
        ),
        None,
    )
    segment_partial = (
        (active.percent / 100.0)
        if active
        else (
            1.0
            if segments
            and any(
                s.segment_key == current_key and s.status == SegmentStatus.COMPLETED
                for s in segments
            )
            else 0.0
        )
    )

    main_percent = int(((completed_before + segment_partial) / total) * 100)
    main_percent = min(100, max(0, main_percent))

    step = flow.get_step(current_key)
    active_segment = None
    if active:
        internal_title = active.internal_step_key or ""
        if active.component_flow_id and active.internal_step_key:
            internal_title = active.internal_step_key.replace("_", " ").title()
        active_segment = SegmentProgress(
            segment_key=active.segment_key,
            orchestrator_id=active.orchestrator_id,
            status=active.status,
            internal_step_key=active.internal_step_key,
            internal_step_title=internal_title,
            percent=active.percent,
        )

    ready = app.status.value != "processing" and (
        active is None or active.status in (SegmentStatus.COMPLETED, SegmentStatus.FAILED)
    )

    return AggregateProgress(
        main_percent=main_percent,
        percent=main_percent,
        current_step=idx + 1,
        total_steps=total,
        current_step_key=current_key,
        current_step_title=step.title if step else current_key,
        active_segment=active_segment,
        ready=ready,
    )
