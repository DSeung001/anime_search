from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from catalog.services.youtube_import import (
    download_to_input_dir,
    extract_youtube_video_id,
    normalize_youtube_url,
)


class YoutubeUrlNormalizeTests(SimpleTestCase):
    def test_watch_url(self) -> None:
        url = normalize_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=foo")
        self.assertEqual(url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(extract_youtube_video_id(url), "dQw4w9WgXcQ")

    def test_youtu_be(self) -> None:
        url = normalize_youtube_url("https://youtu.be/dQw4w9WgXcQ")
        self.assertIn("dQw4w9WgXcQ", url)

    def test_shorts_url(self) -> None:
        vid = extract_youtube_video_id("https://www.youtube.com/shorts/abcdefghijk")
        self.assertEqual(vid, "abcdefghijk")

    def test_rejects_non_youtube(self) -> None:
        with self.assertRaises(ValueError):
            normalize_youtube_url("https://example.com/video")

    def test_rejects_invalid_id(self) -> None:
        with self.assertRaises(ValueError):
            extract_youtube_video_id("https://www.youtube.com/watch?v=tooshort")


@override_settings(YOUTUBE_MAX_DURATION_SEC=100)
class YoutubeDurationLimitTests(SimpleTestCase):
    def test_duration_exceeded(self) -> None:
        from catalog.services.youtube_import import _check_duration_limit

        with self.assertRaises(ValueError):
            _check_duration_limit({"duration": 200})

    def test_duration_ok(self) -> None:
        from catalog.services.youtube_import import _check_duration_limit

        _check_duration_limit({"duration": 50})


class YoutubeDownloadFfmpegTests(SimpleTestCase):
    @override_settings(FFMPEG_BIN="/opt/ffmpeg/bin/ffmpeg")
    def test_passes_ffmpeg_location_to_ytdlp(self) -> None:
        captured: dict = {}

        class FakeYdl:
            def __init__(self, opts: dict) -> None:
                captured.update(opts)

            def __enter__(self) -> "FakeYdl":
                return self

            def __exit__(self, *args: object) -> None:
                pass

            def extract_info(self, url: str, download: bool = False) -> dict:
                return {"duration": 10}

            def download(self, urls: list[str]) -> None:
                pass

        input_dir = Path("/tmp/yt_test_input")
        with (
            patch("yt_dlp.YoutubeDL", FakeYdl),
            patch(
                "catalog.services.youtube_import.find_first_video",
                return_value=Path("/tmp/yt_test_input/youtube_dQw4w9WgXcQ.mp4"),
            ),
        ):
            download_to_input_dir(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                input_dir=input_dir,
            )

        self.assertEqual(captured.get("ffmpeg_location"), "/opt/ffmpeg/bin/ffmpeg")
