from __future__ import annotations

import os
import socket
import ssl
import urllib.request
from typing import Any, Callable, Optional, Tuple

import clip

from anime_indexing.constants import DEFAULT_CLIP_CHECKPOINT_PATH


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _resolved_checkpoint_path(checkpoint_path: Optional[str]) -> str:
    explicit = (checkpoint_path or os.environ.get("CLIP_CHECKPOINT") or "").strip()
    if explicit:
        return explicit
    if DEFAULT_CLIP_CHECKPOINT_PATH.is_file():
        return str(DEFAULT_CLIP_CHECKPOINT_PATH)
    return ""


def load_clip(
    model_name: str,
    device: str,
    *,
    checkpoint_path: Optional[str] = None,
    ssl_no_verify: bool = False,
    download_root: Optional[str] = None,
) -> Tuple[Any, Callable]:
    """`checkpoint_path` / `CLIP_CHECKPOINT` 우선, 없으면 `anime_indexing/weights/ViT-L-14.pt`, 없으면 `model_name` 다운로드."""
    ckpt = _resolved_checkpoint_path(checkpoint_path)
    dl_root = (download_root or os.environ.get("CLIP_DOWNLOAD_ROOT") or "").strip() or None
    no_verify = ssl_no_verify or _truthy_env("CLIP_SSL_NO_VERIFY")

    load_kw: dict[str, Any] = {}
    if dl_root:
        load_kw["download_root"] = dl_root

    if ckpt:
        if not os.path.isfile(ckpt):
            raise FileNotFoundError(f"CLIP 체크포인트가 없습니다: {ckpt}")
        return clip.load(ckpt, device=device, **load_kw)

    if no_verify:
        print(
            "[경고] CLIP_SSL_NO_VERIFY=1 — 모델 다운로드 시 TLS 검증 비활성화. 신뢰할 수 있는 망에서만 사용하세요."
        )
        _orig = urllib.request.urlopen

        def _urlopen_unverified(
            url,
            data=None,
            timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
            *,
            cafile=None,
            capath=None,
            cadefault=False,
            context=None,
        ):
            if context is None:
                context = ssl._create_unverified_context()
            return _orig(
                url,
                data=data,
                timeout=timeout,
                cafile=cafile,
                capath=capath,
                cadefault=cadefault,
                context=context,
            )

        urllib.request.urlopen = _urlopen_unverified  # type: ignore[method-assign]
        try:
            return clip.load(model_name, device=device, **load_kw)
        finally:
            urllib.request.urlopen = _orig  # type: ignore[method-assign]

    return clip.load(model_name, device=device, **load_kw)
