from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Genre
from catalog.services.genre_bulk import bulk_create_genres
from catalog.services.label_ko import normalize_label_ko, parse_label_ko_bulk
from catalog.services.genre_slug import unique_genre_slug


class LabelKoNormalizeTests(TestCase):
    def test_nfkc_casefold(self) -> None:
        self.assertEqual(normalize_label_ko("  액션  "), normalize_label_ko("액션"))

    def test_parse_bulk_dedupes_input(self) -> None:
        labels = parse_label_ko_bulk("액션, 로맨스\n액션")
        self.assertEqual(labels, ["액션", "로맨스"])


class GenreUniqueLabelTests(TestCase):
    def test_duplicate_label_ko_rejected(self) -> None:
        Genre.objects.create(slug=unique_genre_slug("액션"), label_ko="액션")
        with self.assertRaises(ValidationError):
            Genre.objects.create(slug=unique_genre_slug("액션"), label_ko="액션")

    def test_bulk_partial_success(self) -> None:
        Genre.objects.create(slug=unique_genre_slug("기존"), label_ko="기존")
        created, skipped = bulk_create_genres(["기존", "신규"])
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].label_ko, "신규")
        self.assertEqual(len(skipped), 1)
        self.assertIn("기존", skipped[0])
