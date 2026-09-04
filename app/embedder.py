from functools import lru_cache

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from .config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MAX_SEQ_LENGTH,
    EMBEDDING_MODEL,
    MODEL_DEVICE,
)


def resolve_device() -> str:
    if MODEL_DEVICE != "auto":
        return MODEL_DEVICE

    if torch.cuda.is_available():
        return "cuda"

    if (
        hasattr(torch.backends, "mps")
        and torch.backends.mps.is_available()
    ):
        return "mps"

    return "cpu"


@lru_cache(maxsize=1)
def get_embedding_model():
    model = SentenceTransformer(
        EMBEDDING_MODEL,
        device=resolve_device(),
    )

    if hasattr(model, "max_seq_length"):
        model.max_seq_length = EMBEDDING_MAX_SEQ_LENGTH

    return model


def encode_texts(
    texts,
    batch_size: int = EMBEDDING_BATCH_SIZE,
    show_progress_bar: bool = False,
):
    texts = list(texts)

    if not texts:
        return np.empty(
            (0, 0),
            dtype="float32",
        )

    model = get_embedding_model()

    arr = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress_bar,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    return np.asarray(
        arr,
        dtype="float32",
    )
