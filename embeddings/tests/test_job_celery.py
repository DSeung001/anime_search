from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings

from anime_indexing.paths import staging_frames_leaf, staging_input_dir_for_job_frames

from catalog.models import Anime
from embeddings.models import EmbeddingJob
from embeddings.services.job_dispatch import JobDispatchError, enqueue_run_job
from embeddings.services.job_preflight import check_job_input_video
from embeddings.services.job_staging import ensure_job_staging_dirs
from embeddings.tasks import run_embedding_job_task
from embeddings.tests.utils import make_job, staging_with_jpg, staging_with_video


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class JobPreflightTests(TestCase):
    def setUp(self) -> None:
        self.anime = Anime.objects.create(slug="pf_show", title="PF")

    def test_preflight_recreates_removed_staging(self) -> None:
        import shutil

        from anime_indexing.paths import anime_staging_root

        job = make_job(self.anime)
        job_root = anime_staging_root() / "jobs" / str(job.public_id)
        if job_root.is_dir():
            shutil.rmtree(job_root)
        err = check_job_input_video(job)
        self.assertTrue(staging_frames_leaf(job.staging_rel_path).is_dir())
        self.assertIsNotNone(err)
        self.assertIn("input/", err or "")

    def test_input_video_rejects_jpg_only(self) -> None:
        job = make_job(self.anime)
        staging_with_jpg(job)
        err = check_job_input_video(job)
        self.assertIsNotNone(err)
        self.assertIn("input/", err or "")

    def test_input_video_ok_with_mp4(self) -> None:
        job = make_job(self.anime)
        staging_with_video(job)
        self.assertIsNone(check_job_input_video(job))

    def test_create_ensures_staging_dirs(self) -> None:
        job = make_job(self.anime)
        leaf = staging_frames_leaf(job.staging_rel_path)
        self.assertTrue(leaf.is_dir())
        self.assertTrue(staging_input_dir_for_job_frames(leaf).is_dir())


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class EnqueueRunJobTests(TestCase):
    def setUp(self) -> None:
        self.anime = Anime.objects.create(slug="test_show", title="Test")

    def test_enqueue_rejects_jpg_without_video(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.PENDING)
        staging_with_jpg(job)
        with self.assertRaises(JobDispatchError) as ctx:
            enqueue_run_job(job.public_id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("input/", str(ctx.exception))

    def test_enqueue_pending_sets_processing_and_task_id(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.PENDING)
        staging_with_video(job)
        with patch("embeddings.tasks.run_single_embedding_job") as mock_run:
            result = enqueue_run_job(job.public_id)
            mock_run.assert_called_once()
        job.refresh_from_db()
        self.assertEqual(result.public_id, str(job.public_id))
        self.assertTrue(result.celery_task_id)
        self.assertEqual(job.celery_task_id, result.celery_task_id)

    def test_enqueue_rejects_bad_staging(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.PENDING)
        with self.assertRaises(JobDispatchError) as ctx:
            enqueue_run_job(job.public_id)
        self.assertEqual(ctx.exception.status_code, 400)
        job.refresh_from_db()
        self.assertEqual(job.status, EmbeddingJob.Status.PENDING)

    def test_enqueue_rejects_processing(self) -> None:
        job = make_job(
            self.anime,
            status=EmbeddingJob.Status.PROCESSING,
            celery_task_id="existing-task",
        )
        with self.assertRaises(JobDispatchError) as ctx:
            enqueue_run_job(job.public_id)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_enqueue_rejects_non_pending(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.DONE)
        with self.assertRaises(JobDispatchError) as ctx:
            enqueue_run_job(job.public_id)
        self.assertEqual(ctx.exception.status_code, 400)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class RunEmbeddingJobTaskTests(TestCase):
    def setUp(self) -> None:
        self.anime = Anime.objects.create(slug="fail_show", title="Fail")

    def test_task_marks_failed_on_runner_error(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.PROCESSING)
        staging_with_video(job)
        with patch(
            "embeddings.tasks.run_single_embedding_job",
            side_effect=RuntimeError("clip boom"),
        ):
            out = run_embedding_job_task(str(job.public_id))
        job.refresh_from_db()
        self.assertEqual(out["status"], EmbeddingJob.Status.FAILED)
        self.assertEqual(job.status, EmbeddingJob.Status.FAILED)
        self.assertIn("clip boom", job.last_error)

    def test_task_fails_preflight_without_runner(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.PROCESSING)
        with patch("embeddings.tasks.run_single_embedding_job") as mock_run:
            out = run_embedding_job_task(str(job.public_id))
            mock_run.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(out["status"], EmbeddingJob.Status.FAILED)
        self.assertIn("input/", job.last_error)

    def test_task_fails_preflight_jpg_only_without_video(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.PROCESSING)
        staging_with_jpg(job)
        with patch("embeddings.tasks.run_single_embedding_job") as mock_run:
            out = run_embedding_job_task(str(job.public_id))
            mock_run.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(out["status"], EmbeddingJob.Status.FAILED)
        self.assertIn("input/", job.last_error)

    def test_task_not_found(self) -> None:
        out = run_embedding_job_task(str(uuid4()))
        self.assertEqual(out["status"], "not_found")
