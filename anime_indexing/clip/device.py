from __future__ import annotations

import os
import sys

import torch

# auto | cpu | cuda | mps
_VALID_DEVICES = frozenset({"auto", "cpu", "cuda", "mps"})


def default_embed_device_env() -> str:
    """macOS: MPS(Metal) 파이프라인 오류(AGXMetal) 회피를 위해 cpu 기본."""
    if sys.platform == "darwin":
        return "cpu"
    return "auto"


def pick_device() -> str:
    """
    CLIP 추론 디바이스.
    ``ANIME_EMBED_DEVICE``: auto | cpu | cuda | mps (미설정 시 macOS=cpu, 그 외=auto).
    """
    raw = (os.environ.get("ANIME_EMBED_DEVICE") or default_embed_device_env()).strip().lower()
    choice = raw if raw in _VALID_DEVICES else "auto"

    if choice == "cpu":
        return "cpu"
    if choice == "cuda":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if choice == "mps":
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def sync_device(device: str) -> None:
    if device == "cuda" and torch.cuda.is_available():
        torch.cuda.synchronize()
    elif device == "mps" and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        torch.mps.synchronize()
