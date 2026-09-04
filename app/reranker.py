from functools import lru_cache
from typing import List

import numpy as np
import torch
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
)

from .config import (
    ENABLE_RERANKER,
    MODEL_DEVICE,
    RERANK_BATCH_SIZE,
    RERANK_MAX_LENGTH,
    RERANKER_MODEL,
)


def _resolve_device() -> str:
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
def get_reranker():
    tokenizer = AutoTokenizer.from_pretrained(
        RERANKER_MODEL
    )

    model = (
        AutoModelForSequenceClassification
        .from_pretrained(
            RERANKER_MODEL
        )
    )

    device = _resolve_device()

    model.to(device)
    model.eval()

    return (
        tokenizer,
        model,
        device,
    )


def rerank(
    query: str,
    passages: List[str],
) -> List[float]:
    if not passages:
        return []

    if not ENABLE_RERANKER:
        return [
            0.5
            for _ in passages
        ]

    tokenizer, model, device = get_reranker()

    all_scores = []

    with torch.inference_mode():
        for start in range(
            0,
            len(passages),
            RERANK_BATCH_SIZE,
        ):
            batch = passages[
                start:
                start + RERANK_BATCH_SIZE
            ]

            pairs = [
                (
                    query,
                    passage,
                )
                for passage in batch
            ]

            encoded = tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=RERANK_MAX_LENGTH,
                return_tensors="pt",
            )

            encoded = {
                key: value.to(device)
                for key, value in encoded.items()
            }

            output = model(
                **encoded,
                return_dict=True,
            )

            logits = (
                output.logits
                .view(-1)
                .float()
            )

            scores = torch.sigmoid(
                logits
            ).detach().cpu().numpy()

            all_scores.extend(
                float(x)
                for x in scores
            )

    return all_scores
