from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.conf import settings
from django.http import HttpRequest
from google import genai
from google.genai import types

from discovery.models import ChatMessage, ChatSession
from discovery.services.presenter import present_scenes
from discovery.services.retrieval import SearchPipelineError, run_scene_search

SYSTEM_PROMPT = """당신은 애니메이션 장면 검색 도우미입니다.
- 사용자와 한국어로 대화합니다.
- 장면을 찾아야 할 때 search_scenes 도구를 호출하세요.
- search_query에는 잡담을 빼고 시각적으로 그릴 수 있는 장면만 1~2문장으로 적으세요.
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


def _execute_search_scenes(args: dict[str, Any], request: HttpRequest) -> tuple[str, list[dict[str, Any]]]:
    search_query = (args.get("search_query") or "").strip()
    if not search_query:
        return json.dumps({"error": "search_query required"}, ensure_ascii=False), []

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
        segments = run_scene_search(
            search_query=search_query,
            anime_slug=anime_slug,
            episode=ep,
            genre_slugs=gs,
        )
    except SearchPipelineError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False), []

    scenes = present_scenes(segments, request)
    return json.dumps({"count": len(scenes), "scenes": scenes}, ensure_ascii=False), scenes


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
            args = _function_call_args(fc)
            tool_json, scenes = _execute_search_scenes(args, request)
            ChatMessage.objects.create(
                session=session,
                role=ChatMessage.Role.TOOL,
                content=tool_json[:8000],
                tool_name="search_scenes",
                tool_payload={"scenes": scenes, "args": args},
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
