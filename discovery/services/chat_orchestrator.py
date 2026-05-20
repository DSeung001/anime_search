from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.conf import settings
from django.http import HttpRequest
from google import genai
from google.genai import types

from anime_indexing.observability.pipeline_tracer import PipelineTracer
from discovery.models import ChatMessage, ChatSession
from discovery.services.retrieval import SearchPipelineError, run_scene_search

SYSTEM_PROMPT = """당신은 애니메이션 장면 검색 도우미입니다.
- 사용자와 한국어로 대화합니다.
- 장면을 찾아야 할 때 search_scenes 도구를 호출하세요.
- search_query에는 잡담을 빼고 시각적으로 그릴 수 있는 장면만 한국어로 1~2문장 적으세요.
- CLIP 검색용 영어 변환은 서버 파이프라인에서 처리합니다. search_query는 한국어 시각 묘사만 넣으세요.
- 도구 결과에 없는 타임스탬프·URL·제목을 만들지 마세요.
"""

SEARCH_SCENES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "search_query": {"type": "string", "description": "시각 검색용 짧은 문장"},
        "anime_id": {"type": "string", "description": "시리즈 슬러그 (선택)"},
        "episode": {"type": "integer", "description": "화수 (선택)"},
        "genre_slugs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "장르 슬러그 (선택)",
        },
    },
    "required": ["search_query"],
}

SEARCH_SCENES_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="search_scenes",
            description="CLIP 벡터 DB에서 장면 후보를 검색합니다.",
            parameters_json_schema=SEARCH_SCENES_SCHEMA,
        )
    ]
)

_GENERATE_CONFIG = types.GenerateContentConfig(
    tools=[SEARCH_SCENES_TOOL],
    system_instruction=SYSTEM_PROMPT,
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)


class ChatOrchestratorError(Exception):
    pass


def _function_call_args(fc: types.FunctionCall) -> dict[str, Any]:
    raw = fc.args
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    return dict(raw)


def _search_trace_status(scenes: list[dict[str, Any]]) -> str:
    if scenes:
        return "ok"
    return "empty"


def _execute_search_scenes(
    args: dict[str, Any],
    request: HttpRequest,
    *,
    session: ChatSession,
) -> tuple[str, list[dict[str, Any]], str, str, UUID | None]:
    search_query = (args.get("search_query") or "").strip()
    tracer = PipelineTracer.start_search(session_id=session.id)
    trace_id = tracer.trace_id

    if not search_query:
        tracer.stage("error", message="search_query required")
        tracer.finish(status="error", summary="search_query required")
        return json.dumps({"error": "search_query required"}, ensure_ascii=False), [], "", "", trace_id

    anime_slug = (args.get("anime_id") or "").strip() or None
    ep_raw = args.get("episode")
    ep: int | None = None
    if ep_raw is not None and ep_raw != "":
        try:
            ep = int(ep_raw)
        except (TypeError, ValueError):
            ep = None

    gs_raw = args.get("genre_slugs")
    gs: list[str] | None = None
    if isinstance(gs_raw, list):
        gs = [str(x).strip() for x in gs_raw if str(x).strip()]

    try:
        clip_query, scenes = run_scene_search(
            search_query=search_query,
            anime_slug=anime_slug,
            episode=ep,
            genre_slugs=gs,
            tracer=tracer,
            request=request,
        )
    except SearchPipelineError as exc:
        error_msg = str(exc)
        tracer.stage("pipeline_error", message=error_msg)
        tracer.finish(status="error", summary=error_msg[:512])
        return (
            json.dumps({"error": error_msg}, ensure_ascii=False),
            [],
            search_query,
            search_query,
            trace_id,
        )

    tracer.finish(
        status=_search_trace_status(scenes),
        summary=f"scenes={len(scenes)} ko={search_query[:80]}",
    )
    payload = {
        "count": len(scenes),
        "scenes": scenes,
        "search_query_ko": search_query,
        "search_query_en": clip_query,
        "trace_id": str(trace_id),
    }
    return json.dumps(payload, ensure_ascii=False), scenes, search_query, clip_query, trace_id


def _build_user_prompt(session: ChatSession, user_message: str) -> str:
    max_h = int(getattr(settings, "CHAT_MAX_HISTORY", 20))
    msgs = list(session.messages.order_by("-created_at")[:max_h])
    msgs.reverse()
    lines: list[str] = []
    for m in msgs:
        if m.role == ChatMessage.Role.USER:
            lines.append(f"사용자: {m.content}")
        elif m.role == ChatMessage.Role.ASSISTANT:
            lines.append(f"어시스턴트: {m.content}")
    ctx = "\n".join(lines)
    if not ctx:
        return user_message
    return f"이전 대화:\n{ctx}\n\n현재 사용자 메시지: {user_message}"


def _gemini_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
    if not api_key:
        raise ChatOrchestratorError("GEMINI_API_KEY가 설정되지 않았습니다.")
    return genai.Client(api_key=api_key)


def _model_id() -> str:
    return getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")


def run_chat_turn(
    *,
    session: ChatSession,
    user_message: str,
    request: HttpRequest,
) -> tuple[str, list[dict[str, Any]]]:
    client = _gemini_client()
    model = _model_id()

    ChatMessage.objects.create(session=session, role=ChatMessage.Role.USER, content=user_message)

    prompt = _build_user_prompt(session, user_message)
    user_content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)],
    )

    scenes: list[dict[str, Any]] = []
    searched = False
    contents: list[types.Content] = [user_content]
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=_GENERATE_CONFIG,
    )

    for _ in range(3):
        fn_calls = list(response.function_calls or [])
        if not fn_calls:
            break

        function_call_content = response.candidates[0].content if response.candidates else None
        if function_call_content is None:
            break

        tool_response_parts: list[types.Part] = []
        for fc in fn_calls:
            if fc.name != "search_scenes":
                continue
            searched = True
            args = _function_call_args(fc)
            tool_json, scenes, query_ko, query_en, trace_id = _execute_search_scenes(
                args, request, session=session
            )
            tool_payload: dict[str, Any] = {
                "scenes": scenes,
                "args": args,
                "search_query_ko": query_ko,
                "search_query_en": query_en,
            }
            if trace_id:
                tool_payload["trace_id"] = str(trace_id)
            ChatMessage.objects.create(
                session=session,
                role=ChatMessage.Role.TOOL,
                content=tool_json[:8000],
                tool_name="search_scenes",
                tool_payload=tool_payload,
            )
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": tool_json},
                )
            )

        if not tool_response_parts:
            break

        contents = [
            user_content,
            function_call_content,
            types.Content(role="tool", parts=tool_response_parts),
        ]
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=_GENERATE_CONFIG,
        )

    if not searched:
        no_tool_tracer = PipelineTracer.start_search(session_id=session.id)
        no_tool_tracer.stage("gemini_no_tool", user_message_preview=user_message[:300])
        no_tool_tracer.finish(status="empty", summary="gemini_no_tool")

    reply_text = (response.text or "").strip()
    if not reply_text:
        reply_text = (
            f"{len(scenes)}개의 장면 후보를 찾았습니다."
            if scenes
            else "조건에 맞는 장면을 찾지 못했습니다. 설명을 조금 바꿔 보시겠어요?"
        )

    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content=reply_text,
        tool_payload={"scenes": scenes} if scenes else None,
    )
    session.save(update_fields=["updated_at"])
    return reply_text, scenes


def get_or_create_session(session_id: UUID | None) -> ChatSession:
    if session_id:
        found = ChatSession.objects.filter(id=session_id).first()
        if found:
            return found
    return ChatSession.objects.create()
