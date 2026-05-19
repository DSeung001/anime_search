from __future__ import annotations

from celery import shared_task


@shared_task(name="discovery.encode_search_query")
def encode_search_query_task(search_query: str) -> list[float]:
    from anime_indexing.frame_directory_embedding import get_vision_worker

    worker = get_vision_worker()
    vec = worker.encode_text_query(search_query)
    return vec.tolist()
