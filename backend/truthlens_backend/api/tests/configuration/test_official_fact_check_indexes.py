from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.test import SimpleTestCase
from pgvector.django import HnswIndex

from api.models import OfficialFactCheck, _official_fact_check_indexes


POSTGRESQL_ENGINE = "django.db.backends.postgresql"
SQLITE_ENGINE = "django.db.backends.sqlite3"

POSTGRESQL_INDEX_NAMES = {
    "official_claim_hnsw_idx",
    "official_claim_gin_idx",
    "factcheck_status_published_idx",
    "factcheck_org_status_idx",
}
PORTABLE_INDEX_FIELDS = {
    "factcheck_status_published_idx": [
        "publication_status",
        "-published_at",
    ],
    "factcheck_org_status_idx": [
        "organization",
        "publication_status",
    ],
}


def _indexes_by_name(database_engine):
    return {
        index.name: index
        for index in _official_fact_check_indexes(database_engine)
    }


class OfficialFactCheckIndexCompatibilityTests(SimpleTestCase):
    databases = set()

    def test_model_metadata_uses_configured_backend_selection(self):
        engine = settings.DATABASES["default"]["ENGINE"]
        expected_names = set(_indexes_by_name(engine))
        actual_names = {index.name for index in OfficialFactCheck._meta.indexes}

        self.assertEqual(actual_names, expected_names)

    def test_postgresql_retains_complete_index_set(self):
        indexes = _indexes_by_name(POSTGRESQL_ENGINE)

        self.assertEqual(set(indexes), POSTGRESQL_INDEX_NAMES)

    def test_sqlite_excludes_postgresql_specific_indexes(self):
        indexes = _indexes_by_name(SQLITE_ENGINE)

        self.assertNotIn("official_claim_hnsw_idx", indexes)
        self.assertNotIn("official_claim_gin_idx", indexes)

    def test_sqlite_retains_both_portable_indexes(self):
        indexes = _indexes_by_name(SQLITE_ENGINE)

        self.assertEqual(set(indexes), set(PORTABLE_INDEX_FIELDS))
        for name, fields in PORTABLE_INDEX_FIELDS.items():
            with self.subTest(index=name):
                self.assertEqual(indexes[name].fields, fields)

    def test_postgresql_retains_hnsw_definition(self):
        hnsw_index = _indexes_by_name(POSTGRESQL_ENGINE)[
            "official_claim_hnsw_idx"
        ]

        self.assertIsInstance(hnsw_index, HnswIndex)
        self.assertEqual(hnsw_index.fields, ["embedding"])
        self.assertEqual(hnsw_index.m, 16)
        self.assertEqual(hnsw_index.ef_construction, 128)
        self.assertEqual(hnsw_index.opclasses, ["vector_cosine_ops"])

    def test_postgresql_retains_gin_and_portable_index_definitions(self):
        indexes = _indexes_by_name(POSTGRESQL_ENGINE)
        gin_index = indexes["official_claim_gin_idx"]

        self.assertIsInstance(gin_index, GinIndex)
        self.assertEqual(gin_index.fields, ["search_vector"])
        for name, fields in PORTABLE_INDEX_FIELDS.items():
            with self.subTest(index=name):
                self.assertEqual(indexes[name].fields, fields)
