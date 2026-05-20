from __future__ import annotations

import logging
import re
from typing import Final

from django.conf import settings
from google.genai import types

from discovery.services.gemini_client import get_gemini_client, get_gemini_model_id

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
        client = get_gemini_client()
        response = client.models.generate_content(
            model=get_gemini_model_id(),
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
