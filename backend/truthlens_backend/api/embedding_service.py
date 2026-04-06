"""
Embedding Service
═════════════════
Generates 384-dimensional sentence embeddings using the all-MiniLM-L6-v2 model.
Uses a singleton pattern to load the model once and reuse it across calls.

Used by:
  - claim_matching.py (semantic fallback in find_matching_claim)
  - tasks.py (_save_claim persists embeddings)
  - backfill_embeddings management command
"""

from sentence_transformers import SentenceTransformer

# Singleton model instance — loaded lazily on first use
_model = None


def _get_model():
    """Load the embedding model (singleton — only loaded once per process)."""
    global _model
    if _model is None:
        print("Loading sentence-transformers model (all-MiniLM-L6-v2)...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("Embedding model loaded successfully!")
    return _model


def generate_embedding(text):
    """
    Generate a 384-dimensional embedding vector for the given text.

    Args:
        text: The claim text to embed (should be the cleaned_claim / context_text)

    Returns:
        list[float]: A 384-dimensional embedding vector, or None if text is
                     insufficient or an error occurs.
    """
    if not text or len(text.strip()) < 10:
        return None

    try:
        model = _get_model()
        # encode() returns a numpy array; convert to Python list for pgvector
        embedding = model.encode(text.strip(), normalize_embeddings=True)
        return embedding.tolist()
    except Exception as e:
        print(f"Embedding generation failed: {e}")
        return None
