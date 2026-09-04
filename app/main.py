from typing import Optional

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
)
from pydantic import BaseModel, Field

from .config import (
    DEFAULT_TOP_K,
    DEFAULT_WORKERS,
    EMBEDDING_MODEL,
    ENABLE_RERANKER,
    MAX_TOP_K,
    OCR_LANGUAGES,
    RERANKER_MODEL,
    SEARCH_PROFILE,
)
from .db import (
    get_stats,
    list_documents,
)
from .indexer import (
    rebuild_search_indexes,
    sync_folder,
)
from .search_engine import (
    debug_search,
    search,
)


app = FastAPI(
    title="Smart Document Search PRO",
    version="3.0.0",
    description=(
        "Filename-first routing + OCR + incremental indexing + "
        "exact/BM25 + typo char n-gram + BGE semantic + RRF + reranking."
    ),
)

class SyncRequest(BaseModel):
    folder: str = Field(
        ...,
        description=(
            "Folder gốc, ví dụ ./documents"
        ),
    )

    workers: int = Field(
        DEFAULT_WORKERS,
        ge=1,
        le=8,
    )

    use_cache: bool = True


@app.get("/health")
def health():
    return {
        "status": "ok",
        "profile": SEARCH_PROFILE,
        "embedding_model": EMBEDDING_MODEL,
        "reranker_enabled": ENABLE_RERANKER,
        "reranker_model": (
            RERANKER_MODEL
            if ENABLE_RERANKER
            else None
        ),
        "ocr_languages": OCR_LANGUAGES,
        "stats": get_stats(),
    }


@app.post("/sync")
def sync_documents(
    payload: SyncRequest,
):
    try:
        return sync_folder(
            folder=payload.folder,
            workers=payload.workers,
            use_cache=payload.use_cache,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@app.post("/rebuild-search-indexes")
def rebuild_indexes():
    try:
        return rebuild_search_indexes()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.get("/search")
def search_documents(
    q: str = Query(
        ...,
        min_length=1,
    ),
    top_k: int = Query(
        DEFAULT_TOP_K,
        ge=1,
        le=MAX_TOP_K,
    ),
    category: Optional[str] = None,
    folder_prefix: Optional[str] = None,
    extension: Optional[str] = None,
    min_score: Optional[float] = Query(
        None,
        ge=0.0,
        le=1.0,
    ),
):

    try:
        return {
            "query": q,
            "results": search(
                q,
                top_k=top_k,
                category=category,
                folder_prefix=folder_prefix,
                extension=extension,
                min_score=min_score,
            ),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.get("/search/debug")
def search_debug(
    q: str = Query(
        ...,
        min_length=1,
    ),
    top_k: int = Query(
        10,
        ge=1,
        le=50,
    ),
):

    try:
        return debug_search(
            q,
            top_k=top_k,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.get("/documents")
def documents(
    source_root: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(
        200,
        ge=1,
        le=1000,
    ),
    offset: int = Query(
        0,
        ge=0,
    ),
):
    return {
        "results": list_documents(
            source_root=source_root,
            category=category,
            status=status,
            limit=limit,
            offset=offset,
        )
    }


@app.get("/stats")
def stats(
    source_root: Optional[str] = None,
):
    return get_stats(
        source_root=source_root
    )

