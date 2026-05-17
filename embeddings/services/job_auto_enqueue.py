from __future__ import annotations

import logging
from uuid import UUID

from django.db import transaction

logger = logging.getLogger(__name__)


def try_auto_enqueue_job(public_id: UUID) -> bool:
    """
    pending 잡을 Celery에 넣는다.
    스테이징 미준비 등으로 거부되면 False, enqueue 성공 시 True.
    """
    from embeddings.services.job_dispatch import JobDispatchError, enqueue_run_job

    try:
        enqueue_run_job(public_id)
    except JobDispatchError as exc:
        logger.info("auto enqueue skipped public_id=%s: %s", public_id, exc)
        return False
    except Exception:
        logger.exception("auto enqueue failed public_id=%s", public_id)
        return False
    return True


def schedule_auto_enqueue_on_commit(public_id: UUID) -> None:
    """DB 커밋 후 자동 enqueue."""
    pid = public_id

    def _enqueue() -> None:
        try_auto_enqueue_job(pid)

    transaction.on_commit(_enqueue)
