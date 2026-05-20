from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from catalog.models import Anime
from embeddings.models import EmbeddingJob


@override_settings(DEBUG=True)
class AnimeUploadYoutubeTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.anime = Anime.objects.create(slug="yt_upload", title="Upload")

    def test_youtube_url_creates_importing_job(self) -> None:
        mock_delay = MagicMock()
        mock_delay.return_value.id = "task-import-1"

        with patch(
            "catalog.views.import_youtube_video_task.delay",
            mock_delay,
        ):
            resp = self.client.post(
                reverse("catalog_anime_upload"),
                {
                    "anime_slug": self.anime.slug,
                    "episode": "1",
                    "youtube_url": "https://youtu.be/dQw4w9WgXcQ",
                },
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                },
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), EmbeddingJob.Status.IMPORTING)
        self.assertIn("poll_url", data)

        job = EmbeddingJob.objects.get(public_id=data["public_id"])
        self.assertEqual(job.status, EmbeddingJob.Status.IMPORTING)
        self.assertIn("dQw4w9WgXcQ", job.youtube_source_url)
        mock_delay.assert_called_once()

    def test_rejects_file_and_url_together(self) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        resp = self.client.post(
            reverse("catalog_anime_upload"),
            {
                "anime_slug": self.anime.slug,
                "episode": "1",
                "youtube_url": "https://youtu.be/dQw4w9WgXcQ",
                "video": SimpleUploadedFile("a.mp4", b"x", content_type="video/mp4"),
            },
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            },
        )
        self.assertEqual(resp.status_code, 400)
