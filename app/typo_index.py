from functools import lru_cache
from threading import RLock

import joblib
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from .config import (
    TYPO_IDS_PATH,
    TYPO_MATRIX_PATH,
    TYPO_VECTORIZER_PATH,
)
from .db import get_all_chunks_for_typo


_LOCK = RLock()


def _clear_cache():
    load_typo_artifacts.cache_clear()


@lru_cache(maxsize=1)
def load_typo_artifacts():
    if not (
        TYPO_VECTORIZER_PATH.exists()
        and TYPO_MATRIX_PATH.exists()
        and TYPO_IDS_PATH.exists()
    ):
        return None

    vectorizer = joblib.load(
        TYPO_VECTORIZER_PATH
    )

    matrix = sparse.load_npz(
        TYPO_MATRIX_PATH
    )

    ids = np.load(
        TYPO_IDS_PATH
    )

    return (
        vectorizer,
        matrix,
        ids,
    )


def rebuild_typo_index():

    with _LOCK:
        rows = get_all_chunks_for_typo()

        if not rows:
            for p in (
                TYPO_VECTORIZER_PATH,
                TYPO_MATRIX_PATH,
                TYPO_IDS_PATH,
            ):
                if p.exists():
                    p.unlink()

            _clear_cache()

            return {
                "typo_rows": 0
            }

        ids = np.asarray(
            [
                row[0]
                for row in rows
            ],
            dtype="int64",
        )

        corpus = [
            row[1]
            for row in rows
        ]

        vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            lowercase=False,
            min_df=1,
            sublinear_tf=True,
            norm="l2",
            dtype=np.float32,
        )

        matrix = vectorizer.fit_transform(
            corpus
        )

        joblib.dump(
            vectorizer,
            TYPO_VECTORIZER_PATH,
        )

        sparse.save_npz(
            TYPO_MATRIX_PATH,
            matrix,
        )

        np.save(
            TYPO_IDS_PATH,
            ids,
        )

        _clear_cache()

        return {
            "typo_rows": len(ids),
            "typo_features": len(
                vectorizer.vocabulary_
            ),
        }


def typo_search(
    query_norm: str,
    limit: int,
):
    artifacts = load_typo_artifacts()

    if artifacts is None:
        return []

    vectorizer, matrix, ids = artifacts

    q = vectorizer.transform(
        [query_norm]
    )

    if q.nnz == 0:
        return []

    scores = (
        matrix @ q.T
    ).toarray().ravel()

    if scores.size == 0:
        return []

    limit = min(
        int(limit),
        scores.size,
    )

    if limit <= 0:
        return []

    if limit == scores.size:
        order = np.argsort(
            -scores
        )
    else:
        idx = np.argpartition(
            -scores,
            limit - 1,
        )[:limit]

        order = idx[
            np.argsort(
                -scores[idx]
            )
        ]

    return [
        int(ids[i])
        for i in order
        if scores[i] > 0
    ]
