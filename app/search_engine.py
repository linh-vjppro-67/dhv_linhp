from typing import Dict, List, Optional

from rapidfuzz import fuzz

from .config import (
    DEFAULT_TOP_K,
    DENSE_LIMIT,
    FILENAME_FIRST_ENABLED,
    LEXICAL_LIMIT,
    MIN_FINAL_SCORE,
    RERANK_CANDIDATES,
    RRF_K,
    RRF_WEIGHT_DENSE,
    RRF_WEIGHT_EXACT,
    RRF_WEIGHT_LEXICAL,
    RRF_WEIGHT_TYPO,
    TYPO_LIMIT,
)
from .db import (
    fetch_chunks_by_ids,
    filter_chunk_ids,
    lexical_search,
)
from .dense_index import dense_search
from .filename_router import (
    filename_first_search,
)
from .normalize import (
    looks_like_short_name_or_identifier,
    normalize_for_search,
)
from .reranker import rerank
from .typo_index import typo_search


def _rrf_add(
    scores: Dict[int, float],
    ranked_ids: List[int],
    weight: float,
):
    for rank, chunk_id in enumerate(
        ranked_ids,
        start=1,
    ):
        scores[chunk_id] = (
            scores.get(
                chunk_id,
                0.0,
            )
            + weight
            / (
                RRF_K
                + rank
            )
        )


def _make_excerpt(
    text: str,
    max_chars: int = 420,
):
    text = " ".join(
        text.split()
    ).strip()

    if len(text) <= max_chars:
        return text

    return (
        text[:max_chars]
        .rstrip()
        + "..."
    )


def _build_passage(
    row: dict,
) -> str:
    return (
        f"Tên tài liệu: "
        f"{row['file_name']}\n"
        f"Loại tài liệu: "
        f"{row['category']}\n"
        f"Nội dung: "
        f"{row['content']}"
    )


def _apply_filters(
    ids: List[int],
    category: Optional[str],
    folder_prefix: Optional[str],
    extension: Optional[str],
) -> List[int]:
    return filter_chunk_ids(
        ids,
        category=category,
        folder_prefix=folder_prefix,
        extension=extension,
    )


def _retrieve_smart(
    query: str,
    category: Optional[str],
    folder_prefix: Optional[str],
    extension: Optional[str],
):
    query_norm = normalize_for_search(
        query
    )

    exact_ids = lexical_search(
        query_norm,
        limit=min(
            LEXICAL_LIMIT,
            50,
        ),
        phrase=True,
        category=category,
        folder_prefix=folder_prefix,
        extension=extension,
    )

    lexical_ids = lexical_search(
        query_norm,
        limit=LEXICAL_LIMIT,
        phrase=False,
        category=category,
        folder_prefix=folder_prefix,
        extension=extension,
    )

    typo_ids = typo_search(
        query_norm,
        limit=TYPO_LIMIT,
    )

    typo_ids = _apply_filters(
        typo_ids,
        category,
        folder_prefix,
        extension,
    )

    dense_ids = dense_search(
        query,
        limit=DENSE_LIMIT,
    )

    dense_ids = _apply_filters(
        dense_ids,
        category,
        folder_prefix,
        extension,
    )

    fusion = {}

    _rrf_add(
        fusion,
        exact_ids,
        RRF_WEIGHT_EXACT,
    )

    _rrf_add(
        fusion,
        lexical_ids,
        RRF_WEIGHT_LEXICAL,
    )

    _rrf_add(
        fusion,
        typo_ids,
        RRF_WEIGHT_TYPO,
    )

    _rrf_add(
        fusion,
        dense_ids,
        RRF_WEIGHT_DENSE,
    )

    ranked = sorted(
        fusion.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    return (
        query_norm,
        ranked,
        {
            "exact": exact_ids,
            "lexical": lexical_ids,
            "typo": typo_ids,
            "dense": dense_ids,
        },
    )


def _score_smart_candidates(
    query: str,
    query_norm: str,
    ranked_fusion,
    rows,
):
    if not ranked_fusion:
        return []

    max_rrf = max(
        score
        for _, score
        in ranked_fusion
    ) or 1.0

    candidate_rows = []

    for (
        chunk_id,
        rrf_score,
    ) in ranked_fusion:
        row = rows.get(
            chunk_id
        )

        if not row:
            continue

        candidate_rows.append(
            (
                chunk_id,
                row,
                rrf_score,
            )
        )

        if (
            len(candidate_rows)
            >= RERANK_CANDIDATES
        ):
            break

    passages = [
        _build_passage(
            row
        )
        for (
            _,
            row,
            _,
        ) in candidate_rows
    ]

    try:
        rerank_scores = rerank(
            query,
            passages,
        )
    except Exception:
        rerank_scores = [
            0.5
            for _ in candidate_rows
        ]

    short_query = (
        looks_like_short_name_or_identifier(
            query
        )
    )

    results = []

    for (
        (
            chunk_id,
            row,
            rrf_score,
        ),
        rerank_score,
    ) in zip(
        candidate_rows,
        rerank_scores,
    ):
        filename_norm = (
            row["file_name_norm"]
            or normalize_for_search(
                row["file_name"]
            )
        )

        content_norm = (
            row["content_norm"]
            or normalize_for_search(
                row["content"]
            )
        )

        filename_fuzzy = (
            fuzz.WRatio(
                query_norm,
                filename_norm,
            )
            / 100.0
            if query_norm
            else 0.0
        )

        exact_filename = bool(
            query_norm
            and query_norm
            in filename_norm
        )

        exact_content = bool(
            query_norm
            and query_norm
            in content_norm
        )

        rrf_norm = min(
            max(
                rrf_score
                / max_rrf,
                0.0,
            ),
            1.0,
        )

        if short_query:
            rerank_w = 0.58
            filename_w = 0.30
            rrf_w = 0.12
        else:
            rerank_w = 0.76
            filename_w = 0.12
            rrf_w = 0.12

        final_score = (
            rerank_w
            * float(
                rerank_score
            )
            + filename_w
            * filename_fuzzy
            + rrf_w
            * rrf_norm
        )

        if exact_filename:
            final_score += 0.12

        if exact_content:
            final_score += 0.06

        final_score = min(
            max(
                final_score,
                0.0,
            ),
            1.0,
        )

        results.append(
            {
                "chunk_id": chunk_id,
                "document_id": int(
                    row[
                        "document_id"
                    ]
                ),
                "file_name": row[
                    "file_name"
                ],
                "category": row[
                    "category"
                ],
                "content": row[
                    "content"
                ],
                "final_score": (
                    final_score
                ),
                "debug": {
                    "reranker": round(
                        float(
                            rerank_score
                        ),
                        6,
                    ),
                    "filename_fuzzy": round(
                        filename_fuzzy,
                        6,
                    ),
                    "rrf": round(
                        rrf_norm,
                        6,
                    ),
                    "exact_filename": (
                        exact_filename
                    ),
                    "exact_content": (
                        exact_content
                    ),
                },
            }
        )

    return results


def _smart_search(
    query: str,
    top_k: int,
    category: Optional[str],
    folder_prefix: Optional[str],
    extension: Optional[str],
    min_score: Optional[float],
):
    (
        query_norm,
        ranked_fusion,
        _,
    ) = _retrieve_smart(
        query,
        category,
        folder_prefix,
        extension,
    )

    if not ranked_fusion:
        return []

    rows = fetch_chunks_by_ids(
        [
            chunk_id
            for (
                chunk_id,
                _,
            )
            in ranked_fusion[
                :max(
                    RERANK_CANDIDATES
                    * 3,
                    100,
                )
            ]
        ]
    )

    scored = (
        _score_smart_candidates(
            query,
            query_norm,
            ranked_fusion,
            rows,
        )
    )

    best_by_document = {}

    for item in scored:
        document_id = item[
            "document_id"
        ]

        old = (
            best_by_document
            .get(
                document_id
            )
        )

        if (
            old is None
            or item["final_score"]
            > old["final_score"]
        ):
            best_by_document[
                document_id
            ] = item

    ranked_documents = sorted(
        best_by_document.values(),
        key=lambda x: x[
            "final_score"
        ],
        reverse=True,
    )

    threshold = (
        MIN_FINAL_SCORE
        if min_score is None
        else float(
            min_score
        )
    )

    compact = []

    for item in ranked_documents:
        if (
            threshold > 0
            and item["final_score"]
            < threshold
        ):
            continue

        compact.append(
            {
                "rank": (
                    len(compact)
                    + 1
                ),
                "file_name": item[
                    "file_name"
                ],
                "category": item[
                    "category"
                ],
                "excerpt": (
                    _make_excerpt(
                        item[
                            "content"
                        ]
                    )
                ),
                "score": round(
                    item[
                        "final_score"
                    ],
                    3,
                ),
            }
        )

        if (
            len(compact)
            >= top_k
        ):
            break

    return compact


def search(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    category: Optional[str] = None,
    folder_prefix: Optional[str] = None,
    extension: Optional[str] = None,
    min_score: Optional[float] = None,
):
    
    query = query.strip()

    if not query:
        return []

    if FILENAME_FIRST_ENABLED:
        direct = (
            filename_first_search(
                query,
                category=category,
                folder_prefix=folder_prefix,
                extension=extension,
            )
        )

        if direct:
            return direct

    return _smart_search(
        query=query,
        top_k=top_k,
        category=category,
        folder_prefix=folder_prefix,
        extension=extension,
        min_score=min_score,
    )


def debug_search(
    query: str,
    top_k: int = 10,
):
    """
    Debug cho developer:
    cho biết query được route filename hay smart.
    """
    direct = filename_first_search(
        query
    )

    if direct:
        return {
            "query": query,
            "route": (
                "filename_first"
            ),
            "results": direct,
        }

    (
        query_norm,
        ranked_fusion,
        retrievers,
    ) = _retrieve_smart(
        query,
        category=None,
        folder_prefix=None,
        extension=None,
    )

    rows = fetch_chunks_by_ids(
        [
            chunk_id
            for (
                chunk_id,
                _,
            )
            in ranked_fusion[
                :max(
                    RERANK_CANDIDATES
                    * 3,
                    100,
                )
            ]
        ]
    )

    scored = (
        _score_smart_candidates(
            query,
            query_norm,
            ranked_fusion,
            rows,
        )
    )

    scored = sorted(
        scored,
        key=lambda x: x[
            "final_score"
        ],
        reverse=True,
    )

    return {
        "query": query,
        "route": "smart",
        "query_norm": (
            query_norm
        ),
        "retriever_counts": {
            key: len(value)
            for (
                key,
                value,
            ) in retrievers.items()
        },
        "candidates": (
            scored[:top_k]
        ),
    }
