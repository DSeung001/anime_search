from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from anime_indexing.video.frame_timestamps import compute_frame_timestamps_sec
from anime_indexing.video.pts_manifest import MANIFEST_FILENAME, sorted_frame_jpgs


class FrameTimestampsTests(TestCase):
    def _make_frames(self, count: int) -> tuple[Path, list[Path]]:
        tmp = Path(tempfile.mkdtemp())
        jpgs: list[Path] = []
        for i in range(count):
            name = f"frame_{i + 1:06d}.jpg"
            p = tmp / name
            p.write_bytes(b"\xff\xd8\xff")
            jpgs.append(p)
        return tmp, sorted_frame_jpgs(tmp)

    @override_settings(VIDEO_EXTRACT_FPS=1.0)
    def test_extract_fps_1_no_manifest(self) -> None:
        leaf, jpgs = self._make_frames(3)
        times, source = compute_frame_timestamps_sec(jpgs, leaf)
        self.assertEqual(source, "extract_fps")
        self.assertEqual(times, [0.0, 1.0, 2.0])

    @override_settings(VIDEO_EXTRACT_FPS=2.0)
    def test_extract_fps_2(self) -> None:
        leaf, jpgs = self._make_frames(3)
        times, source = compute_frame_timestamps_sec(jpgs, leaf)
        self.assertEqual(source, "extract_fps")
        self.assertEqual(times, [0.0, 0.5, 1.0])

    @override_settings(VIDEO_EXTRACT_FPS=0.0)
    def test_full_frame_requires_manifest(self) -> None:
        leaf, jpgs = self._make_frames(2)
        with self.assertRaises(RuntimeError) as ctx:
            compute_frame_timestamps_sec(jpgs, leaf)
        self.assertIn("VIDEO_EXTRACT_FPS", str(ctx.exception))

    @override_settings(VIDEO_EXTRACT_FPS=0.0)
    def test_full_frame_uses_manifest(self) -> None:
        leaf, jpgs = self._make_frames(2)
        manifest = leaf / MANIFEST_FILENAME
        with manifest.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"file": jpgs[0].name, "pts_sec": 10.0}) + "\n")
            f.write(json.dumps({"file": jpgs[1].name, "pts_sec": 20.5}) + "\n")
        times, source = compute_frame_timestamps_sec(jpgs, leaf)
        self.assertEqual(source, "pts_manifest")
        self.assertEqual(times, [10.0, 20.5])
