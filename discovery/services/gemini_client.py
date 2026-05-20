from __future__ import annotations

from django.conf import settings
from google import genai


def get_gemini_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
    return genai.Client(api_key=api_key)


def get_gemini_model_id() -> str:
    return getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
