from threading import RLock

import faiss
import numpy as np

from .config import FAISS_PATH
from .db import get_all_chunks_for_dense
from .embedder import encode_texts


_LOCK = RLock()
_INDEX = None


def _new_index(dim: int):
    base = faiss.IndexFlatIP(dim)
    return faiss.IndexIDMap2(base)


def _atomic_write(index):
    tmp = FAISS_PATH.with_suffix(".faiss.tmp")
    faiss.write_index(
        index,
        str(tmp),
    )
    tmp.replace(FAISS_PATH)


def load_index():
    global _INDEX

    with _LOCK:
        if _INDEX is not None:
            return _INDEX

        if FAISS_PATH.exists():
            _INDEX = faiss.read_index(
                str(FAISS_PATH)
            )
            return _INDEX

        return None


def rebuild_dense_from_db():
    global _INDEX

    with _LOCK:
        rows = get_all_chunks_for_dense()

        if not rows:
            _INDEX = None

            if FAISS_PATH.exists():
                FAISS_PATH.unlink()

            return {
                "vectors": 0
            }

        ids = [
            row[0]
            for row in rows
        ]

        texts = [
            row[1]
            for row in rows
        ]

        vectors = encode_texts(
            texts,
            show_progress_bar=True,
        )

        index = _new_index(
            int(vectors.shape[1])
        )

        index.add_with_ids(
            vectors,
            np.asarray(
                ids,
                dtype="int64",
            ),
        )

        _atomic_write(index)
        _INDEX = index

        return {
            "vectors": len(ids)
        }


def apply_dense_changes(
    remove_ids,
    add_ids,
    add_vectors,
):
    global _INDEX

    remove_ids = [
        int(i)
        for i in remove_ids
    ]

    add_ids = [
        int(i)
        for i in add_ids
    ]

    with _LOCK:
        index = load_index()

        if index is None and add_ids:
            if add_vectors.size == 0:
                raise ValueError(
                    "Có add_ids nhưng không có add_vectors."
                )

            index = _new_index(
                int(add_vectors.shape[1])
            )

        if (
            index is not None
            and remove_ids
        ):
            index.remove_ids(
                np.asarray(
                    remove_ids,
                    dtype="int64",
                )
            )

        if (
            index is not None
            and add_ids
        ):
            index.add_with_ids(
                np.asarray(
                    add_vectors,
                    dtype="float32",
                ),
                np.asarray(
                    add_ids,
                    dtype="int64",
                ),
            )

        if (
            index is None
            or index.ntotal == 0
        ):
            _INDEX = None

            if FAISS_PATH.exists():
                FAISS_PATH.unlink()

            return

        _atomic_write(index)
        _INDEX = index


def dense_search(
    query: str,
    limit: int,
):
    index = load_index()

    if (
        index is None
        or index.ntotal == 0
    ):
        return []

    q = encode_texts(
        [query],
        batch_size=1,
        show_progress_bar=False,
    )

    limit = max(
        1,
        min(
            int(limit),
            int(index.ntotal),
        ),
    )

    _, ids = index.search(
        q,
        limit,
    )

    return [
        int(i)
        for i in ids[0].tolist()
        if int(i) >= 0
    ]
