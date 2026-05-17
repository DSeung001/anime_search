from __future__ import annotations

"""
단건 수동 실행용. ``process_embedding_jobs`` 의 ``select_for_update`` 큐와는 별도 경로이므로,
같은 ``public_id`` 에 대해 워커와 이 명령을 동시에 돌리지 말 것(경쟁 상태·이중 처리 위험).
운영 보안·큐 정책은 별도 검토 보류.
"""

from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from anime_indexing.embedding_job_runner import run_single_embedding_job

from embeddings.models import EmbeddingJob


class Command(BaseCommand):
    help = "지정한 public_id(pending) 작업 한 건을 즉시 파이프라인 실행(추출·승격·CLIP·Qdrant)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("public_id", type=str, help="EmbeddingJob.public_id (UUID)")

    def handle(self, *args, **options) -> None:
        uid = UUID(options["public_id"])
        job = EmbeddingJob.objects.filter(public_id=uid).first()
        if job is None:
            raise CommandError("작업을 찾을 수 없습니다.")
        if job.status != EmbeddingJob.Status.PENDING:
            raise CommandError(f"pending 상태만 실행 가능합니다 (현재: {job.status})")

        job.status = EmbeddingJob.Status.PROCESSING
        job.save(update_fields=["status", "updated_at"])

        try:
            run_single_embedding_job(job)
        except Exception as exc:  # noqa: BLE001
            job.status = EmbeddingJob.Status.FAILED
            job.last_error = str(exc)[:4000]
            job.save(update_fields=["status", "last_error", "updated_at"])
            self.stderr.write(self.style.ERROR(str(exc)))
            raise

        self.stdout.write(self.style.SUCCESS("완료"))
