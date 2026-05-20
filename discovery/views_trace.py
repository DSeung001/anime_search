from __future__ import annotations

import json
from uuid import UUID

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from catalog.views import _ui_gate
from discovery.models import PipelineTrace


@require_GET
def trace_list(request: HttpRequest) -> HttpResponse:
    gate = _ui_gate(request)
    if gate is not None:
        return gate

    qs = PipelineTrace.objects.select_related("session").all()
    kind = (request.GET.get("kind") or "").strip()
    if kind in (PipelineTrace.Kind.SEARCH, PipelineTrace.Kind.INDEXING):
        qs = qs.filter(kind=kind)
    session_raw = (request.GET.get("session_id") or "").strip()
    if session_raw:
        try:
            qs = qs.filter(session_id=UUID(session_raw))
        except ValueError:
            pass
    job_raw = (request.GET.get("job_public_id") or "").strip()
    if job_raw:
        try:
            qs = qs.filter(job_public_id=UUID(job_raw))
        except ValueError:
            pass

    traces = list(qs[:100])
    return render(
        request,
        "discovery/trace_list.html",
        {
            "traces": traces,
            "filter_kind": kind,
            "filter_session_id": session_raw,
            "filter_job_public_id": job_raw,
        },
    )


@require_GET
def trace_detail(request: HttpRequest, trace_id: UUID) -> HttpResponse:
    gate = _ui_gate(request)
    if gate is not None:
        return gate

    trace = get_object_or_404(PipelineTrace.objects.select_related("session"), id=trace_id)
    payload_pretty = json.dumps(trace.payload, ensure_ascii=False, indent=2, default=str)
    stages_raw = list((trace.payload or {}).get("stages") or [])
    stages = [
        {
            "name": s.get("name", "?"),
            "data_pretty": json.dumps(
                s.get("data") or {},
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        }
        for s in stages_raw
    ]
    return render(
        request,
        "discovery/trace_detail.html",
        {
            "trace": trace,
            "stages": stages,
            "payload_pretty": payload_pretty,
        },
    )
