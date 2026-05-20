from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from django.db.models import Count, OuterRef, Subquery

from discovery.models import ChatMessage, ChatSession
from discovery.services.chat_orchestrator import ChatSessionNotFoundError

_PREVIEW_LEN = 80


def _truncate(text: str, max_len: int = _PREVIEW_LEN) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _first_user_content(session_id: UUID) -> str:
    row = (
        ChatMessage.objects.filter(session_id=session_id, role=ChatMessage.Role.USER)
        .order_by("created_at")
        .values_list("content", flat=True)
        .first()
    )
    return (row or "").strip()


def list_recent_sessions(*, limit: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 100))
    first_user = ChatMessage.objects.filter(
        session_id=OuterRef("pk"),
        role=ChatMessage.Role.USER,
    ).order_by("created_at")
    sessions = (
        ChatSession.objects.annotate(
            message_count=Count("messages"),
            first_user_content=Subquery(first_user.values("content")[:1]),
        )
        .order_by("-updated_at")[:lim]
    )
    out: list[dict[str, Any]] = []
    for s in sessions:
        preview = _truncate(s.first_user_content or "") or "(대화 없음)"
        out.append(
            {
                "id": str(s.id),
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
                "preview": preview,
                "message_count": int(s.message_count or 0),
            }
        )
    return out


def _extract_last_scenes(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    for m in reversed(messages):
        payload = m.tool_payload if isinstance(m.tool_payload, dict) else None
        if not payload:
            continue
        scenes = payload.get("scenes")
        if isinstance(scenes, list) and scenes:
            return scenes
    return []


def _message_to_api_row(m: ChatMessage) -> dict[str, Any]:
    row: dict[str, Any] = {
        "role": m.role,
        "content": m.content,
        "created_at": m.created_at.isoformat(),
    }
    if m.role == ChatMessage.Role.TOOL:
        row["tool_name"] = m.tool_name
        payload = m.tool_payload if isinstance(m.tool_payload, dict) else {}
        row["search_query_ko"] = payload.get("search_query_ko") or ""
        scenes = payload.get("scenes")
        row["scene_count"] = len(scenes) if isinstance(scenes, list) else 0
    return row


def get_session_messages(session_id: UUID) -> dict[str, Any]:
    session = ChatSession.objects.filter(id=session_id).first()
    if session is None:
        raise ChatSessionNotFoundError(f"session not found: {session_id}")

    messages = list(session.messages.order_by("created_at"))
    api_messages: list[dict[str, Any]] = [_message_to_api_row(m) for m in messages]

    return {
        "session_id": str(session.id),
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "preview": _truncate(_first_user_content(session.id)) or "(대화 없음)",
        "messages": api_messages,
        "last_scenes": _extract_last_scenes(messages),
    }


def format_session_updated(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def sessions_for_template(*, limit: int = 50) -> list[dict[str, Any]]:
    """채팅 목록 템플릿용: ``list_recent_sessions`` + 표시용 ``updated_label``."""
    out: list[dict[str, Any]] = []
    for row in list_recent_sessions(limit=limit):
        item = dict(row)
        item["updated_label"] = format_session_updated(datetime.fromisoformat(row["updated_at"]))
        item["id"] = UUID(row["id"])
        out.append(item)
    return out
