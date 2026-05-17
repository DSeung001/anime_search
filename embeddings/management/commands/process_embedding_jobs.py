from __future__ import annotations

"""표준 워커 진입점. ``anime_indexing.embedding_job_runner.process_next_pending_job`` 가
``select_for_update`` 로 한 건씩 잠근다. 수동 실행은 ``run_embedding_job`` (별도 경로·보류 정책 참고).
"""

from django.core.management.base import BaseCommand

from anime_indexing.embedding_job_runner import process_next_pending_job


class Command(BaseCommand):
    help = "pending 임베딩 작업을 하나씩 처리한다 (스테이징 승격 → CLIP → Qdrant)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--loop",
            action="store_true",
            help="처리할 작업이 없을 때까지 반복한다.",
        )

    def handle(self, *args, **options) -> None:
        if options["loop"]:
            while process_next_pending_job():
                self.stdout.write(self.style.SUCCESS("processed one job"))
            self.stdout.write("no pending jobs")
            return

        if process_next_pending_job():
            self.stdout.write(self.style.SUCCESS("processed one job"))
        else:
            self.stdout.write("no pending jobs")
