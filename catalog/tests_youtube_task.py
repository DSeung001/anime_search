from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings

from catalog.tasks import import_youtube_video_task
from embeddings.models import EmbeddingJob
from catalog.models import Anime
from embeddings.test_utils import make_job


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class ImportYoutubeTaskTests(TestCase):
    def setUp(self) -> None:
        self.anime = Anime.objects.create(slug="yt_task", title="YT")

    def test_success_sets_pending_and_enqueues(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.IMPORTING)
        job.youtube_source_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        job.save(update_fields=["youtube_source_url", "updated_at"])

        fake_video = Path("youtube_dQw4w9WgXcQ.mp4")

        with (
            patch(
                "catalog.tasks.download_to_input_dir",
                return_value=fake_video,
            ) as mock_dl,
            patch("catalog.tasks.try_auto_enqueue_job", return_value=True) as mock_enqueue,
        ):
            result = import_youtube_video_task(
                str(job.public_id),
                job.youtube_source_url,
            )

        mock_dl.assert_called_once()
        mock_enqueue.assert_called_once_with(job.public_id)
        job.refresh_from_db()
        self.assertEqual(job.status, EmbeddingJob.Status.PENDING)
        self.assertEqual(job.source_video_filename, fake_video.name)
        self.assertEqual(result["status"], EmbeddingJob.Status.PENDING)

    def test_skip_when_not_importing(self) -> None:
        job = make_job(self.anime)
        job.status = EmbeddingJob.Status.PENDING
        job.save(update_fields=["status", "updated_at"])

        with patch("catalog.tasks.download_to_input_dir") as mock_dl:
            result = import_youtube_video_task(
                str(job.public_id),
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            )

        mock_dl.assert_not_called()
        self.assertEqual(result["status"], EmbeddingJob.Status.PENDING)

    def test_failure_marks_failed(self) -> None:
        job = make_job(self.anime, status=EmbeddingJob.Status.IMPORTING)

        with patch(
            "catalog.tasks.download_to_input_dir",
            side_effect=RuntimeError("yt-dlp boom"),
        ):
            result = import_youtube_video_task(
                str(job.public_id),
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            )

        job.refresh_from_db()
        self.assertEqual(job.status, EmbeddingJob.Status.FAILED)
        self.assertIn("yt-dlp boom", job.last_error)
        self.assertEqual(result["status"], EmbeddingJob.Status.FAILED)

    def test_not_found(self) -> None:
        result = import_youtube_video_task(
            str(uuid4()),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        self.assertEqual(result["status"], "not_found")
