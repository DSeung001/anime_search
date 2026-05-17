from __future__ import annotations

import tempfile
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from anime_indexing.paths import anime_staging_root, ensure_dir, frames_leaf_under_media

from catalog.models import Anime
from embeddings.models import EmbeddingJob
from embeddings.services.job_delete import JobDeleteError, delete_embedding_job


class JobDeleteServiceTests(TestCase):
    def setUp(self) -> None:
        self._media_tmp = tempfile.TemporaryDirectory()
        self._staging_tmp = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            ANIME_MEDIA_ROOT=self._media_tmp.name,
            ANIME_STAGING_ROOT=self._staging_tmp.name,
        )
        self.settings_override.enable()
        self.anime = Anime.objects.create(slug="del_show", title="Del")

    def tearDown(self) -> None:
        self.settings_override.disable()
        self._media_tmp.cleanup()
        self._staging_tmp.cleanup()

    def _staging_root_for(self, job: EmbeddingJob) -> None:
        root = anime_staging_root() / "jobs" / str(job.public_id)
        ensure_dir(root / "frames")
        (root / "frames" / "a.jpg").write_bytes(b"\xff\xd8\xff")

    def test_delete_pending_removes_db_and_staging(self) -> None:
        job = EmbeddingJob.objects.create(anime=self.anime, status=EmbeddingJob.Status.PENDING)
        self._staging_root_for(job)
        staging_path = anime_staging_root() / "jobs" / str(job.public_id)
        public_id = job.public_id

        with patch("embeddings.services.job_delete.delete_points_for_job_public_id") as mock_q:
            delete_embedding_job(public_id=public_id)
            mock_q.assert_called_once_with(public_id)

        self.assertFalse(EmbeddingJob.objects.filter(public_id=public_id).exists())
        self.assertFalse(staging_path.exists())

    def test_delete_processing_raises(self) -> None:
        job = EmbeddingJob.objects.create(
            anime=self.anime,
            status=EmbeddingJob.Status.PROCESSING,
        )
        with self.assertRaises(JobDeleteError) as ctx:
            delete_embedding_job(public_id=job.public_id)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertTrue(EmbeddingJob.objects.filter(pk=job.pk).exists())

    def test_delete_done_removes_canonical_when_latest(self) -> None:
        job = EmbeddingJob.objects.create(
            anime=self.anime,
            status=EmbeddingJob.Status.DONE,
            processed_at=timezone.now(),
        )
        leaf = frames_leaf_under_media(self.anime.slug)
        ensure_dir(leaf)
        (leaf / "frame.jpg").write_bytes(b"\xff\xd8\xff")

        with patch("embeddings.services.job_delete.delete_points_for_job_public_id"):
            delete_embedding_job(public_id=job.public_id)

        self.assertFalse(EmbeddingJob.objects.filter(pk=job.pk).exists())
        self.assertFalse((leaf / "frame.jpg").exists())

    def test_delete_older_done_keeps_canonical(self) -> None:
        older_time = timezone.now() - timedelta(hours=2)
        newer_time = timezone.now() - timedelta(hours=1)
        older = EmbeddingJob.objects.create(
            anime=self.anime,
            status=EmbeddingJob.Status.DONE,
            processed_at=older_time,
        )
        EmbeddingJob.objects.create(
            anime=self.anime,
            status=EmbeddingJob.Status.DONE,
            processed_at=newer_time,
        )
        leaf = frames_leaf_under_media(self.anime.slug)
        ensure_dir(leaf)
        (leaf / "frame.jpg").write_bytes(b"\xff\xd8\xff")

        with patch("embeddings.services.job_delete.delete_points_for_job_public_id"):
            delete_embedding_job(public_id=older.public_id)

        self.assertTrue((leaf / "frame.jpg").exists())

    def test_delete_not_found(self) -> None:
        with self.assertRaises(JobDeleteError) as ctx:
            delete_embedding_job(public_id=uuid4())
        self.assertEqual(ctx.exception.status_code, 404)


@override_settings(DEBUG=True)
class JobDeleteApiTests(TestCase):
    def setUp(self) -> None:
        self._media_tmp = tempfile.TemporaryDirectory()
        self._staging_tmp = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            ANIME_MEDIA_ROOT=self._media_tmp.name,
            ANIME_STAGING_ROOT=self._staging_tmp.name,
        )
        self.settings_override.enable()
        self.client = Client()
        self.anime = Anime.objects.create(slug="api_del", title="API")

    def tearDown(self) -> None:
        self.settings_override.disable()
        self._media_tmp.cleanup()
        self._staging_tmp.cleanup()

    def test_api_delete_success(self) -> None:
        job = EmbeddingJob.objects.create(anime=self.anime, status=EmbeddingJob.Status.FAILED)
        url = reverse("catalog_job_api_delete", kwargs={"public_id": job.public_id})
        with patch("embeddings.services.job_delete.delete_points_for_job_public_id"):
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["deleted"])
        self.assertFalse(EmbeddingJob.objects.filter(pk=job.pk).exists())

    def test_api_delete_processing_409(self) -> None:
        job = EmbeddingJob.objects.create(
            anime=self.anime,
            status=EmbeddingJob.Status.PROCESSING,
        )
        url = reverse("catalog_job_api_delete", kwargs={"public_id": job.public_id})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 409)
        self.assertIn("처리 중", resp.json()["detail"])
