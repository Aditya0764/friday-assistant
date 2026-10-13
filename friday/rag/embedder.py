"""Lazy sentence embeddings (all-MiniLM-L6-v2, 384 dimensions).

The model is loaded on first use, not at startup, to save RAM (risk R2).
"""

from __future__ import annotations

import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIMENSION = 384

_model = None


def get_model():
    """Load the model the first time it is needed, then reuse it."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(texts: list[str]) -> np.ndarray:
    """Return a float32 array of shape (len(texts), 384), unit length (cosine = dot product)."""
    vectors = get_model().encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype="float32")