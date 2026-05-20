from __future__ import annotations

import logging
import re
from typing import Final

from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_TRANSLATE_SYSTEM: Final[str] = """You convert anime scene search phrases into concise English visual descriptions for CLIP text-image matching.
Rules:
- Output English only, 1-2 short sentences.
- Describe only what can be seen in a frame (characters, pose, setting, lighting, colors).
- Do not include episode numbers, titles, URLs, or conversational filler.
- No quotes or markdown."""

_ASCII_RE = re.compile(r"[\x00-\x7F]+")


def _ascii_ratio(text: str) -> float:
    if not text:
        return 1.0
    ascii_chars = len(_ASCII_RE.findall(text))
    return ascii_chars / max(len(text), 1)


def _gemini_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
    return genai.Client(api_key=api_key)


def _model_id() -> str:
    return getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")


def translate_search_query_for_clip(search_query: str) -> str:
    """CLIP용 영어 시각 묘사로 변환. 실패 시 원문 반환."""
    raw = (search_query or "").strip()
    if not raw:
        return raw

    if not getattr(settings, "SEARCH_QUERY_TRANSLATE_ENABLED", True):
        return raw

    if _ascii_ratio(raw) >= 0.85:
        return raw

    try:
        client = _gemini_client()
        response = client.models.generate_content(
            model=_model_id(),
            contents=raw,
            config=types.GenerateContentConfig(
                system_instruction=_TRANSLATE_SYSTEM,
                temperature=0.1,
            ),
        )
        translated = (response.text or "").strip()
        if translated:
            return translated
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_query EN translate failed, using original: %s", exc)

    return raw
