from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def qdrant_is_configured() -> bool:
    """``QDRANT_URL`` 이 있고 ``qdrant-client`` 를 import 할 수 있을 때만 True."""
    url = getattr(settings, "QDRANT_URL", "") or ""
    if not url:
        return False
    try:
        import qdrant_client  # noqa: F401
    except ImportError:
        return False
    return True


def get_qdrant_client_and_collection() -> tuple[Any | None, str | None]:
    """(QdrantClient | None, collection_name | None). 미설정·import 실패 시 (None, None)."""
    url = getattr(settings, "QDRANT_URL", "") or ""
    if not url:
        return None, None
    try:
        from qdrant_client import QdrantClient  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("QDRANT_URL이 설정됐지만 qdrant-client가 설치되지 않았습니다.")
        return None, None
    client = QdrantClient(url=url, api_key=settings.QDRANT_API_KEY or None)
    return client, settings.QDRANT_COLLECTION
