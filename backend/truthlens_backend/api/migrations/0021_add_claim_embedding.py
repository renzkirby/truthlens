"""
Migration: Add claim_embedding VectorField for semantic similarity matching.
Enables the pgvector extension and adds a 384-dimensional embedding field
with an HNSW index for fast approximate nearest neighbor search.
"""

from django.db import migrations
from pgvector.django import VectorField, HnswIndex, VectorExtension


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0020_add_claim_fingerprint"),
    ]

    operations = [
        # Ensure pgvector extension is active in PostgreSQL
        VectorExtension(),

        # Add the embedding vector field
        migrations.AddField(
            model_name="claim",
            name="claim_embedding",
            field=VectorField(
                dimensions=384,
                null=True,
                blank=True,
                help_text="384-dim embedding vector from all-MiniLM-L6-v2 for semantic claim matching",
            ),
        ),

        # Add HNSW index for fast approximate nearest neighbor search
        migrations.AddIndex(
            model_name="claim",
            index=HnswIndex(
                name="claim_embedding_hnsw_idx",
                fields=["claim_embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]
