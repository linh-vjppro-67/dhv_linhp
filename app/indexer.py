from concurrent.futures import (
    ProcessPoolExecutor,
    as_completed,
)
from pathlib import Path
from threading import Lock
from typing import Optional

import numpy as np

from .chunker import chunk_units
from .config import DEFAULT_WORKERS
from .db import (
    delete_document,
    get_documents_for_root,
    get_stats,
    init_db,
    mark_document_error,
    update_same_content,
    upsert_document_success,
)
from .dense_index import (
    apply_dense_changes,
    rebuild_dense_from_db,
)
from .embedder import encode_texts
from .extractors import extract_file
from .normalize import normalize_for_search
from .scanner import discover_files
from .typo_index import rebuild_typo_index
from .types import ExtractedUnit, FileInfo
from .utils import now_iso, sha256_file


_SYNC_LOCK = Lock()


def _serialize_info(info: FileInfo):
    return {
        "source_root": info.source_root,
        "absolute_path": info.absolute_path,
        "relative_path": info.relative_path,
        "file_name": info.file_name,
        "extension": info.extension,
        "category": info.category,
        "folder_path": info.folder_path,
        "file_size": info.file_size,
        "modified_ns": info.modified_ns,
    }


def _deserialize_info(data):
    return FileInfo(**data)


def _extract_worker(
    info_data,
    old_hash: Optional[str],
    use_cache: bool,
):
    info = _deserialize_info(
        info_data
    )

    path = Path(
        info.absolute_path
    )

    try:
        file_hash = sha256_file(
            path
        )

        if (
            old_hash
            and old_hash == file_hash
        ):
            return {
                "ok": True,
                "same_content": True,
                "info": info_data,
                "file_hash": file_hash,
                "cached": True,
                "units": [],
            }

        (
            file_hash,
            units,
            cached,
        ) = extract_file(
            path,
            file_hash=file_hash,
            use_cache=use_cache,
        )

        return {
            "ok": True,
            "same_content": False,
            "info": info_data,
            "file_hash": file_hash,
            "cached": cached,
            "units": [
                {
                    "text": u.text,
                    "page_no": u.page_no,
                    "extraction_mode": u.extraction_mode,
                }
                for u in units
            ],
        }

    except Exception as exc:
        return {
            "ok": False,
            "same_content": False,
            "info": info_data,
            "file_hash": None,
            "cached": False,
            "units": [],
            "error": str(exc),
        }


def _run_extract_jobs(
    candidates,
    db_docs,
    workers: int,
    use_cache: bool,
    force_reextract: bool = False,
):
    jobs = []

    for info in candidates:
        old = db_docs.get(
            info.relative_path
        )

        old_hash = None if force_reextract else (
            old.get("sha256")
            if old
            else None
        )

        jobs.append(
            (
                _serialize_info(info),
                old_hash,
                use_cache,
            )
        )

    if (
        workers <= 1
        or len(jobs) <= 1
    ):
        return [
            _extract_worker(
                info_data,
                old_hash,
                use_cache_flag,
            )
            for (
                info_data,
                old_hash,
                use_cache_flag,
            ) in jobs
        ]

    results = []

    with ProcessPoolExecutor(
        max_workers=workers
    ) as pool:
        futures = [
            pool.submit(
                _extract_worker,
                info_data,
                old_hash,
                use_cache_flag,
            )
            for (
                info_data,
                old_hash,
                use_cache_flag,
            ) in jobs
        ]

        for future in as_completed(
            futures
        ):
            results.append(
                future.result()
            )

    return results


def _embedding_text(
    info: FileInfo,
    content: str,
):
    return (
        f"Tên tài liệu: {info.file_name}\n"
        f"Loại: {info.category}\n"
        f"Nội dung: {content}"
    )


def sync_folder(
    folder: str,
    workers: int = DEFAULT_WORKERS,
    use_cache: bool = True,
    force_reextract: bool = False,
):
    if not _SYNC_LOCK.acquire(
        blocking=False
    ):
        raise RuntimeError(
            "Một phiên sync khác đang chạy."
        )

    try:
        init_db()

        scanned = discover_files(
            folder
        )

        if not scanned:
            raise ValueError(
                "Không tìm thấy PDF/DOCX/TXT/MD."
            )

        source_root = (
            scanned[0].source_root
        )

        current = {
            f.relative_path: f
            for f in scanned
        }

        db_docs = get_documents_for_root(
            source_root
        )

        new_files = []
        changed_files = []
        unchanged_files = []

        for rel, info in current.items():
            old = db_docs.get(rel)

            if old is None:
                new_files.append(info)
                continue

            if (not force_reextract and
                int(old["file_size"])
                == int(info.file_size)
                and int(old["modified_ns"])
                == int(info.modified_ns)
                and old["status"] == "indexed"
            ):
                unchanged_files.append(
                    info
                )
            else:
                changed_files.append(
                    info
                )

        deleted_rels = sorted(
            set(db_docs)
            - set(current)
        )

        stats = {
            "source_root": source_root,
            "scanned_files": len(scanned),
            "new": len(new_files),
            "changed": len(changed_files),
            "unchanged": len(
                unchanged_files
            ),
            "deleted": len(deleted_rels),
            "same_content_after_hash": 0,
            "processed": 0,
            "cached_extractions": 0,
            "ocr_pages": 0,
            "native_pdf_pages": 0,
            "chunks_added": 0,
            "errors": [],
            "started_at": now_iso(),
        }

        vector_remove_ids = []

        for rel in deleted_rels:
            old = db_docs[rel]

            vector_remove_ids.extend(
                delete_document(
                    int(old["id"])
                )
            )

        candidates = (
            new_files
            + changed_files
        )

        worker_results = _run_extract_jobs(
            candidates,
            db_docs,
            workers=max(
                1,
                int(workers),
            ),
            use_cache=use_cache,
            force_reextract=force_reextract,
        )

        prepared = []

        for result in worker_results:
            info = _deserialize_info(
                result["info"]
            )

            if not result["ok"]:
                mark_document_error(
                    info,
                    error=result.get(
                        "error",
                        "Unknown error",
                    ),
                    file_hash=result.get(
                        "file_hash"
                    ),
                )

                stats["errors"].append(
                    {
                        "file": info.relative_path,
                        "error": result.get(
                            "error",
                            "Unknown error",
                        ),
                    }
                )
                continue

            if result["same_content"]:
                update_same_content(
                    info,
                    result["file_hash"],
                )

                stats[
                    "same_content_after_hash"
                ] += 1

                continue

            units = [
                ExtractedUnit(
                    text=u["text"],
                    page_no=u.get(
                        "page_no"
                    ),
                    extraction_mode=u[
                        "extraction_mode"
                    ],
                )
                for u in result["units"]
            ]

            chunks = chunk_units(
                units
            )

            if not chunks:
                mark_document_error(
                    info,
                    error=(
                        "Không trích xuất "
                        "được text/chunk nào."
                    ),
                    file_hash=result[
                        "file_hash"
                    ],
                )

                stats["errors"].append(
                    {
                        "file": info.relative_path,
                        "error": (
                            "Không trích xuất "
                            "được text/chunk nào."
                        ),
                    }
                )
                continue

            ocr_pages = sum(
                1
                for u in units
                if u.extraction_mode
                == "ocr_pdf"
            )

            native_pages = sum(
                1
                for u in units
                if u.extraction_mode
                == "native_pdf"
            )

            prepared.append(
                {
                    "info": info,
                    "file_hash": result[
                        "file_hash"
                    ],
                    "chunks": chunks,
                    "ocr_pages": ocr_pages,
                    "native_pages": native_pages,
                    "cached": bool(
                        result["cached"]
                    ),
                }
            )

        all_embedding_texts = []
        offsets = []
        cursor = 0

        for item in prepared:
            texts = [
                _embedding_text(
                    item["info"],
                    chunk.content,
                )
                for chunk in item["chunks"]
            ]

            all_embedding_texts.extend(
                texts
            )

            offsets.append(
                (
                    cursor,
                    cursor + len(texts),
                )
            )

            cursor += len(texts)

        if all_embedding_texts:
            all_vectors = encode_texts(
                all_embedding_texts,
                show_progress_bar=True,
            )
        else:
            all_vectors = None

        vector_add_ids = []
        vector_add_vectors = []

        for item, (
            start,
            end,
        ) in zip(
            prepared,
            offsets,
        ):
            (
                _,
                old_chunk_ids,
                new_chunk_ids,
            ) = upsert_document_success(
                info=item["info"],
                file_hash=item[
                    "file_hash"
                ],
                chunks=item["chunks"],
                ocr_pages=item[
                    "ocr_pages"
                ],
                native_pages=item[
                    "native_pages"
                ],
            )

            vector_remove_ids.extend(
                old_chunk_ids
            )

            vector_add_ids.extend(
                new_chunk_ids
            )

            if all_vectors is not None:
                vector_add_vectors.extend(
                    all_vectors[
                        start:end
                    ]
                )

            stats["processed"] += 1
            stats["chunks_added"] += len(
                item["chunks"]
            )
            stats["ocr_pages"] += item[
                "ocr_pages"
            ]
            stats[
                "native_pdf_pages"
            ] += item["native_pages"]

            if item["cached"]:
                stats[
                    "cached_extractions"
                ] += 1

        if vector_add_vectors:
            add_vectors = np.asarray(
                vector_add_vectors,
                dtype="float32",
            )
        else:
            add_vectors = np.empty(
                (0, 0),
                dtype="float32",
            )

        changed_anything = bool(
            vector_remove_ids
            or vector_add_ids
        )

        if changed_anything:
            try:
                apply_dense_changes(
                    remove_ids=vector_remove_ids,
                    add_ids=vector_add_ids,
                    add_vectors=add_vectors,
                )
            except Exception:
                rebuild_dense_from_db()

            typo_stats = rebuild_typo_index()
            stats.update(typo_stats)

        stats["finished_at"] = now_iso()
        stats["db"] = get_stats(
            source_root=source_root
        )

        return stats

    finally:
        _SYNC_LOCK.release()


def rebuild_search_indexes():
    dense = rebuild_dense_from_db()
    typo = rebuild_typo_index()

    return {
        **dense,
        **typo,
    }
