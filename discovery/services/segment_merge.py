from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SceneSegment:
    anime_id: str
    episode: int | None
    episode_id: int | None
    job_public_id: str
    frame_index: int
    frame_file: str
    start_sec: float
    end_sec: float
    peak_sec: float
    score: float
    genre: list[str]


def _key(payload: dict[str, Any]) -> tuple[str, int | None, str]:
    ep = payload.get("episode")
    return (
        str(payload.get("anime_id") or ""),
        int(ep) if ep is not None else None,
        str(payload.get("job_public_id") or ""),
    )


def merge_frame_hits(
    hits: list[dict[str, Any]],
    *,
    gap_sec: float = 1.5,
    max_segments: int = 8,
) -> list[SceneSegment]:
    parsed: list[tuple[float, dict[str, Any]]] = []
    for h in hits:
        p = dict(h.get("payload") or {})
        if "timestamp_sec" not in p:
            continue
        parsed.append((float(h.get("score") or 0.0), p))
    if not parsed:
        return []

    parsed.sort(key=lambda x: (_key(x[1]), float(x[1]["timestamp_sec"])))
    out: list[SceneSegment] = []
    cluster: list[tuple[float, dict[str, Any]]] = []
    ckey: tuple[str, int | None, str] | None = None

    def flush() -> None:
        nonlocal cluster, ckey
        if not cluster:
            return
        best_score, best_p = max(cluster, key=lambda x: x[0])
        times = [float(x[1]["timestamp_sec"]) for x in cluster]
        genres = best_p.get("genre")
        out.append(
            SceneSegment(
                anime_id=str(best_p.get("anime_id") or ""),
                episode=int(best_p["episode"]) if best_p.get("episode") is not None else None,
                episode_id=int(best_p["episode_id"]) if best_p.get("episode_id") is not None else None,
                job_public_id=str(best_p.get("job_public_id") or ""),
                frame_index=int(best_p.get("frame_index") or 0),
                frame_file=str(best_p.get("frame_file") or ""),
                start_sec=min(times),
                end_sec=max(times),
                peak_sec=float(best_p["timestamp_sec"]),
                score=best_score,
                genre=list(genres) if isinstance(genres, list) else [],
            )
        )
        cluster = []
        ckey = None

    for score, p in parsed:
        key = _key(p)
        ts = float(p["timestamp_sec"])
        if ckey is None:
            ckey, cluster = key, [(score, p)]
            continue
        if key != ckey:
            flush()
            ckey, cluster = key, [(score, p)]
            continue
        if ts - float(cluster[-1][1]["timestamp_sec"]) > gap_sec:
            flush()
            ckey, cluster = key, [(score, p)]
        else:
            cluster.append((score, p))
    flush()
    out.sort(key=lambda s: s.score, reverse=True)
    return out[:max_segments]
