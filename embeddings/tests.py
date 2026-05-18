from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from anime_indexing.paths import (
    anime_staging_root,
    canonical_frames_key,
    resolve_under_root,
)


class PathTests(SimpleTestCase):
    def test_canonical_frames_key(self) -> None:
        self.assertEqual(canonical_frames_key("my_show", 3), "my_show/episodes/3/frames")

    def test_canonical_frames_key_rejects_slash(self) -> None:
        with self.assertRaises(ValueError):
            canonical_frames_key("a/b", 1)

    def test_canonical_frames_key_rejects_bad_episode(self) -> None:
        with self.assertRaises(ValueError):
            canonical_frames_key("my_show", 0)

    @override_settings(ANIME_STAGING_ROOT="/tmp/anime_staging_test")
    def test_resolve_blocks_traversal(self) -> None:
        root = anime_staging_root()
        with self.assertRaises(ValueError):
            resolve_under_root(root, "../etc/passwd")
