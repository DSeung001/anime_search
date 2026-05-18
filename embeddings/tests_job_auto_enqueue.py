from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, TransactionTestCase, override_settings

from anime_indexing.paths import ensure_dir, staging_frames_leaf, staging_input_dir_for_job_frames

from catalog.models import Anime
from embeddings.models import EmbeddingJob
from embeddings.test_utils import make_job
from embeddings.services.job_auto_enqueue import (
    schedule_auto_enqueue_on_commit,
    try_auto_enqueue_job,
)
from embeddings.services.job_staging import ensure_job_staging_dirs


def _staging_with_jpg(job: EmbeddingJob) -> None:
    leaf = staging_frames_leaf(job.staging_rel_path)
    ensure_dir(leaf)
    ensure_dir(staging_input_dir_for_job_frames(leaf))
    (leaf / "frame_0001.jpg").write_bytes(b"\xff\xd8\xff")


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TryAutoEnqueueTests(TestCase):
    def setUp(self) -> None:
        self.anime = Anime.objects.create(slug="auto_show", title="Auto")

    def test_enqueues_when_staging_ready(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.PENDING)
        _staging_with_jpg(job)
        with patch("embeddings.tasks.run_single_embedding_job"):
            ok = try_auto_enqueue_job(job.public_id)
        self.assertTrue(ok)
        job.refresh_from_db()
        self.assertEqual(job.status, EmbeddingJob.Status.PROCESSING)
        self.assertTrue(job.celery_task_id)

    def test_skips_when_staging_not_ready(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.PENDING)
        ensure_job_staging_dirs(job)
        ok = try_auto_enqueue_job(job.public_id)
        self.assertFalse(ok)
        job.refresh_from_db()
        self.assertEqual(job.status, EmbeddingJob.Status.PENDING)
        self.assertEqual(job.celery_task_id, "")


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class ScheduleOnCommitTests(TransactionTestCase):
    def setUp(self) -> None:
        self.anime = Anime.objects.create(slug="commit_show", title="Commit")

    def test_on_commit_enqueues_after_transaction(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.PENDING)
        _staging_with_jpg(job)
        with patch("embeddings.tasks.run_single_embedding_job"):
            schedule_auto_enqueue_on_commit(job.public_id)
        job.refresh_from_db()
        self.assertEqual(job.status, EmbeddingJob.Status.PROCESSING)
