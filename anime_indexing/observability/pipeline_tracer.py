from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from django.conf import settings

logger = logging.getLogger("anime_search.pipeline")

TraceKind = Literal["search", "indexing"]
TraceStatus = Literal["ok", "error", "empty"]


def trace_enabled() -> bool:
    return bool(getattr(settings, "PIPELINE_TRACE_ENABLED", True))


def _top_hits_limit() -> int:
    return int(getattr(settings, "PIPELINE_TRACE_LOG_TOP_HITS", 10))


def summarize_hits(hits: list[dict[str, Any]], *, top_n: int | None = None) -> list[dict[str, Any]]:
    n = top_n if top_n is not None else _top_hits_limit()
    out: list[dict[str, Any]] = []
    for h in hits[: max(0, n)]:
        p = dict(h.get("payload") or {})
        out.append(
            {
                "score": round(float(h.get("score") or 0.0), 4),
                "anime_id": p.get("anime_id"),
                "episode": p.get("episode"),
                "timestamp_sec": p.get("timestamp_sec"),
                "job_public_id": p.get("job_public_id"),
                "frame_file": p.get("frame_file"),
            }
        )
    return out


@dataclass
class PipelineTracer:
    kind: TraceKind
    trace_id: UUID
    session_id: UUID | None = None
    job_public_id: UUID | None = None
    _stages: list[dict[str, Any]] = field(default_factory=list)
    _enabled: bool = True

    @classmethod
    def start_search(
        cls,
        *,
        session_id: UUID | None = None,
        trace_id: UUID | None = None,
    ) -> PipelineTracer:
        return cls(
            kind="search",
            trace_id=trace_id or uuid.uuid4(),
            session_id=session_id,
            _enabled=trace_enabled(),
        )

    @classmethod
    def start_indexing(
        cls,
        *,
        job_public_id: UUID,
        trace_id: UUID | None = None,
    ) -> PipelineTracer:
        return cls(
            kind="indexing",
            trace_id=trace_id or uuid.uuid4(),
            job_public_id=job_public_id,
            _enabled=trace_enabled(),
        )

    def stage(self, name: str, **data: Any) -> None:
        if not self._enabled:
            return
        self._stages.append({"name": name, "data": data})

    def finish(self, *, status: TraceStatus, summary: str) -> Any | None:
        if not self._enabled:
            return None

        from discovery.models import PipelineTrace

        payload: dict[str, Any] = {
            "trace_id": str(self.trace_id),
            "kind": self.kind,
            "stages": self._stages,
        }
        record = PipelineTrace.objects.create(
            id=self.trace_id,
            kind=self.kind,
            session_id=self.session_id,
            job_public_id=self.job_public_id,
            status=status,
            summary=summary[:512],
            payload=payload,
        )
        log_body = {
            "event": "pipeline_trace",
            "trace_id": str(self.trace_id),
            "kind": self.kind,
            "status": status,
            "summary": summary,
            "stages": self._stages,
        }
        logger.info("%s", json.dumps(log_body, ensure_ascii=False, default=str))
        return record
