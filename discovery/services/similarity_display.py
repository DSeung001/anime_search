from __future__ import annotations

SCORE_FULL_SCALE = 0.25


def similarity_percent(score: float | None) -> int | None:
    if score is None:
        return None
    raw = float(score)
    if raw != raw:  # NaN
        return None
    return min(100, max(0, round(raw / SCORE_FULL_SCALE * 100)))


def format_similarity_label(score: float | None) -> str:
    if score is None:
        return "-"
    raw = float(score)
    pct = similarity_percent(raw)
    if pct is None:
        return "-"
    return f"{pct}%(score: {raw:.2f})"


def build_display_label(
    *,
    anime_title: str,
    episode: int | None,
    episode_title: str,
    time_label: str,
) -> str:
    ep_num = episode if episode is not None else "?"
    ep_title = (episode_title or "").strip()
    return f"({anime_title}) {ep_num}화 {ep_title} {time_label}".strip()
