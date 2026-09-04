from pathlib import Path
from typing import Dict, List, Optional

from rapidfuzz import fuzz

from .config import (
    FILENAME_AMBIGUOUS_LIMIT,
    FILENAME_MAX_RESULTS,
    FILENAME_ROUTE_MIN_SCORE,
    FILENAME_SCORE_WINDOW,
)
from .db import list_filename_documents
from .normalize import normalize_for_search


def _filename_stem_norm(file_name: str) -> str:
    return normalize_for_search(
        Path(file_name).stem
    )


def _best_token_similarity(
    query_tokens: List[str],
    filename_tokens: List[str],
):

    if not query_tokens or not filename_tokens:
        return 0.0, 0.0

    matched = 0
    similarities = []

    for query_token in query_tokens:
        best = max(
            fuzz.ratio(
                query_token,
                filename_token,
            )
            for filename_token in filename_tokens
        )

        similarities.append(
            best / 100.0
        )

        if len(query_token) <= 2:
            threshold = 100
        elif len(query_token) == 3:
            threshold = 80
        else:
            threshold = 70

        if best >= threshold:
            matched += 1

    coverage = matched / len(query_tokens)
    avg_similarity = (
        sum(similarities)
        / len(similarities)
    )

    return coverage, avg_similarity


def score_filename_match(
    query: str,
    file_name: str,
) -> dict:

    query_norm = normalize_for_search(
        query
    )

    filename_norm = _filename_stem_norm(
        file_name
    )

    if not query_norm or not filename_norm:
        return {
            "score": 0.0,
            "strong": False,
            "exact_substring": False,
            "exact_all_tokens": False,
            "token_coverage": 0.0,
            "token_similarity": 0.0,
        }

    query_tokens = query_norm.split()
    filename_tokens = filename_norm.split()

    exact_substring = (
        query_norm in filename_norm
    )

    exact_all_tokens = all(
        token in filename_tokens
        for token in query_tokens
    )

    token_coverage, token_similarity = (
        _best_token_similarity(
            query_tokens,
            filename_tokens,
        )
    )

    wratio = (
        fuzz.WRatio(
            query_norm,
            filename_norm,
        )
        / 100.0
    )

    partial = (
        fuzz.partial_ratio(
            query_norm,
            filename_norm,
        )
        / 100.0
    )

    token_set = (
        fuzz.token_set_ratio(
            query_norm,
            filename_norm,
        )
        / 100.0
    )

    score = max(
        wratio,
        partial * 0.98,
        token_set * 0.96,
    )

    if query_norm == filename_norm:
        score = max(
            score,
            1.0,
        )
    elif exact_substring:
        score = max(
            score,
            0.995,
        )

    if exact_all_tokens:
        score = max(
            score,
            0.975,
        )

    if (
        len(query_tokens) >= 2
        and token_coverage == 1.0
        and token_similarity >= 0.78
    ):
        score = max(
            score,
            0.93
            + min(
                0.04,
                max(
                    0.0,
                    token_similarity - 0.78,
                )
                * 0.18,
            )
        )

    has_digit = any(
        any(ch.isdigit() for ch in token)
        for token in query_tokens
    )

    numeric_tokens = [
        token
        for token in query_tokens
        if token.isdigit()
    ]

    numeric_exact = (
        bool(numeric_tokens)
        and all(
            token in filename_tokens
            for token in numeric_tokens
        )
    )

    if (
        has_digit
        and numeric_exact
        and token_coverage >= 0.75
    ):
        score = max(
            score,
            0.97,
        )

    score = min(
        max(
            float(score),
            0.0,
        ),
        1.0,
    )

    strong = (
        score >= FILENAME_ROUTE_MIN_SCORE
        and (
            exact_substring
            or exact_all_tokens
            or numeric_exact
            or (
                token_coverage == 1.0
                and token_similarity >= 0.78
            )
            or wratio >= 0.90
        )
    )

    return {
        "score": score,
        "strong": strong,
        "exact_substring": exact_substring,
        "exact_all_tokens": exact_all_tokens,
        "numeric_exact": numeric_exact,
        "token_coverage": token_coverage,
        "token_similarity": token_similarity,
        "wratio": wratio,
        "partial": partial,
        "token_set": token_set,
    }


def filename_first_search(
    query: str,
    category: Optional[str] = None,
    folder_prefix: Optional[str] = None,
    extension: Optional[str] = None,
) -> List[dict]:

    query_norm = normalize_for_search(
        query
    )

    if not query_norm:
        return []

    documents = list_filename_documents(
        category=category,
        folder_prefix=folder_prefix,
        extension=extension,
    )

    if not documents:
        return []

    scored = []

    for document in documents:
        match = score_filename_match(
            query,
            document["file_name"],
        )

        if not match["strong"]:
            continue

        scored.append(
            {
                "document_id": int(
                    document["id"]
                ),
                "file_name": document[
                    "file_name"
                ],
                "category": document[
                    "category"
                ],
                "relative_path": document[
                    "relative_path"
                ],
                "score": float(
                    match["score"]
                ),
                "_match": match,
            }
        )

    if not scored:
        return []

    scored.sort(
        key=lambda x: (
            x["score"],
            x["_match"]["exact_substring"],
            x["_match"]["exact_all_tokens"],
        ),
        reverse=True,
    )

    best_score = scored[0]["score"]

    relevant = [
        item
        for item in scored
        if (
            item["score"]
            >= FILENAME_ROUTE_MIN_SCORE
            and item["score"]
            >= (
                best_score
                - FILENAME_SCORE_WINDOW
            )
        )
    ]

    query_tokens = query_norm.split()

    has_digit = any(
        any(ch.isdigit() for ch in token)
        for token in query_tokens
    )

    if (
        not has_digit
        and len(query_tokens) <= 2
        and len(relevant)
        > FILENAME_AMBIGUOUS_LIMIT
    ):
        return []

    relevant = relevant[
        :FILENAME_MAX_RESULTS
    ]

    return [
        {
            "rank": rank,
            "file_name": item["file_name"],
            "category": item["category"],
            "score": round(
                item["score"],
                3,
            ),
        }
        for rank, item in enumerate(
            relevant,
            start=1,
        )
    ]
