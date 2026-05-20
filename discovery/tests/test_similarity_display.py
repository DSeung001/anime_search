from __future__ import annotations

from django.test import SimpleTestCase

from discovery.services.similarity_display import (
    build_display_label,
    format_similarity_label,
    similarity_percent,
)


class SimilarityDisplayTests(SimpleTestCase):
    def test_percent_scale(self) -> None:
        self.assertEqual(similarity_percent(0.25), 100)
        self.assertEqual(similarity_percent(0.2), 80)
        self.assertEqual(similarity_percent(0.3), 100)

    def test_label_format(self) -> None:
        self.assertEqual(format_similarity_label(0.2), "80%(score: 0.20)")

    def test_display_label(self) -> None:
        label = build_display_label(
            anime_title="프리렌",
            episode=3,
            episode_title="마법사의 시험",
            time_label="2:15",
        )
        self.assertEqual(label, "(프리렌) 3화 마법사의 시험 2:15")
