from django.db import connection
from django.test import TestCase


class MeasuredDatabaseIndexTests(TestCase):
    def test_postgresql_trigram_extension_and_search_indexes_exist(self):
        self.assertEqual(connection.vendor, "postgresql")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')"
            )
            self.assertTrue(cursor.fetchone()[0])

            cursor.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND indexname IN (
                    'content_title_trgm_gin',
                    'content_prompt_trgm_gin',
                    'content_body_trgm_gin'
                  )
                """
            )
            indexes = dict(cursor.fetchall())

        self.assertEqual(
            set(indexes),
            {
                "content_title_trgm_gin",
                "content_prompt_trgm_gin",
                "content_body_trgm_gin",
            },
        )
        for definition in indexes.values():
            self.assertIn("USING gin", definition)
            self.assertIn("gin_trgm_ops", definition)
