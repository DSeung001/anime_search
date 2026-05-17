from __future__ import annotations

import re
import unicodedata

_LABEL_KO_MAX = 255

_SPLIT_RE = re.compile(r"[,，\n\r]+")


def normalize_label_ko(raw: str) -> str:
    """strip → NFKC → casefold, max 255 chars."""
    s = unicodedata.normalize("NFKC", (raw or "").strip()).casefold()
    return s[:_LABEL_KO_MAX]


def parse_label_ko_bulk(text: str) -> list[str]:
    """쉼표·줄바꿈으로 분리하고, 정규화 기준 입력 내 중복은 첫 항목만 유지."""
    seen: set[str] = set()
    out: list[str] = []
    for part in _SPLIT_RE.split(text or ""):
        label = (part or "").strip()
        if not label:
            continue
        norm = normalize_label_ko(label)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(label)
    return out
