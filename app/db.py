import sqlite3
from typing import Dict, Iterable, List, Optional

from .config import DB_PATH
from .normalize import normalize_for_search
from .types import Chunk, FileInfo
from .utils import now_iso


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_root TEXT NOT NULL,
    absolute_path TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_name_norm TEXT NOT NULL,
    extension TEXT NOT NULL,
    category TEXT NOT NULL,
    folder_path TEXT NOT NULL,

    file_size INTEGER NOT NULL,
    modified_ns INTEGER NOT NULL,
    sha256 TEXT,

    status TEXT NOT NULL DEFAULT 'pending',
    indexed_at TEXT,
    updated_at TEXT NOT NULL,

    chunk_count INTEGER NOT NULL DEFAULT 0,
    ocr_pages INTEGER NOT NULL DEFAULT 0,
    native_pages INTEGER NOT NULL DEFAULT 0,

    error TEXT,

    UNIQUE(source_root, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_documents_root
    ON documents(source_root);

CREATE INDEX IF NOT EXISTS idx_documents_category
    ON documents(category);

CREATE INDEX IF NOT EXISTS idx_documents_path
    ON documents(relative_path);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    page_no INTEGER,
    chunk_no INTEGER NOT NULL,
    extraction_mode TEXT NOT NULL,
    content TEXT NOT NULL,
    content_norm TEXT NOT NULL,

    FOREIGN KEY(document_id)
        REFERENCES documents(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_document
    ON chunks(document_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    content_norm,
    file_name,
    file_name_norm,
    category,
    tokenize = "unicode61 remove_diacritics 2"
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def get_documents_for_root(source_root: str) -> Dict[str, dict]:
    init_db()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM documents
            WHERE source_root = ?
            """,
            (source_root,),
        ).fetchall()

    return {
        row["relative_path"]: dict(row)
        for row in rows
    }


def get_document_chunk_ids(document_id: int) -> List[int]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM chunks
            WHERE document_id = ?
            """,
            (document_id,),
        ).fetchall()

    return [int(row["id"]) for row in rows]


def delete_document(document_id: int) -> List[int]:
    old_ids = get_document_chunk_ids(document_id)

    with connect() as conn:
        for chunk_id in old_ids:
            conn.execute(
                """
                DELETE FROM chunks_fts
                WHERE rowid = ?
                """,
                (chunk_id,),
            )

        conn.execute(
            """
            DELETE FROM chunks
            WHERE document_id = ?
            """,
            (document_id,),
        )

        conn.execute(
            """
            DELETE FROM documents
            WHERE id = ?
            """,
            (document_id,),
        )

        conn.commit()

    return old_ids


def update_same_content(
    info: FileInfo,
    file_hash: str,
):
    with connect() as conn:
        conn.execute(
            """
            UPDATE documents
            SET
                absolute_path = ?,
                file_name = ?,
                file_name_norm = ?,
                extension = ?,
                category = ?,
                folder_path = ?,
                file_size = ?,
                modified_ns = ?,
                sha256 = ?,
                updated_at = ?,
                status = 'indexed',
                error = NULL
            WHERE source_root = ?
              AND relative_path = ?
            """,
            (
                info.absolute_path,
                info.file_name,
                normalize_for_search(info.file_name),
                info.extension,
                info.category,
                info.folder_path,
                info.file_size,
                info.modified_ns,
                file_hash,
                now_iso(),
                info.source_root,
                info.relative_path,
            ),
        )
        conn.commit()


def mark_document_error(
    info: FileInfo,
    error: str,
    file_hash: Optional[str] = None,
):
    init_db()

    with connect() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM documents
            WHERE source_root = ?
              AND relative_path = ?
            """,
            (
                info.source_root,
                info.relative_path,
            ),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE documents
                SET
                    absolute_path = ?,
                    file_name = ?,
                    file_name_norm = ?,
                    extension = ?,
                    category = ?,
                    folder_path = ?,
                    file_size = ?,
                    modified_ns = ?,
                    sha256 = COALESCE(?, sha256),
                    status = 'error',
                    updated_at = ?,
                    error = ?
                WHERE id = ?
                """,
                (
                    info.absolute_path,
                    info.file_name,
                    normalize_for_search(info.file_name),
                    info.extension,
                    info.category,
                    info.folder_path,
                    info.file_size,
                    info.modified_ns,
                    file_hash,
                    now_iso(),
                    error,
                    int(existing["id"]),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO documents(
                    source_root,
                    absolute_path,
                    relative_path,
                    file_name,
                    file_name_norm,
                    extension,
                    category,
                    folder_path,
                    file_size,
                    modified_ns,
                    sha256,
                    status,
                    indexed_at,
                    updated_at,
                    chunk_count,
                    ocr_pages,
                    native_pages,
                    error
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    'error',
                    NULL,
                    ?,
                    0, 0, 0,
                    ?
                )
                """,
                (
                    info.source_root,
                    info.absolute_path,
                    info.relative_path,
                    info.file_name,
                    normalize_for_search(info.file_name),
                    info.extension,
                    info.category,
                    info.folder_path,
                    info.file_size,
                    info.modified_ns,
                    file_hash,
                    now_iso(),
                    error,
                ),
            )

        conn.commit()


def upsert_document_success(
    info: FileInfo,
    file_hash: str,
    chunks: List[Chunk],
    ocr_pages: int,
    native_pages: int,
):
    """
    Return:
        document_id, old_chunk_ids, new_chunk_ids
    """
    init_db()

    file_name_norm = normalize_for_search(info.file_name)

    with connect() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM documents
            WHERE source_root = ?
              AND relative_path = ?
            """,
            (
                info.source_root,
                info.relative_path,
            ),
        ).fetchone()

        old_chunk_ids = []

        if existing:
            document_id = int(existing["id"])

            rows = conn.execute(
                """
                SELECT id
                FROM chunks
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchall()

            old_chunk_ids = [
                int(row["id"])
                for row in rows
            ]

            for chunk_id in old_chunk_ids:
                conn.execute(
                    """
                    DELETE FROM chunks_fts
                    WHERE rowid = ?
                    """,
                    (chunk_id,),
                )

            conn.execute(
                """
                DELETE FROM chunks
                WHERE document_id = ?
                """,
                (document_id,),
            )

            conn.execute(
                """
                UPDATE documents
                SET
                    absolute_path = ?,
                    file_name = ?,
                    file_name_norm = ?,
                    extension = ?,
                    category = ?,
                    folder_path = ?,
                    file_size = ?,
                    modified_ns = ?,
                    sha256 = ?,
                    status = 'indexed',
                    indexed_at = ?,
                    updated_at = ?,
                    chunk_count = ?,
                    ocr_pages = ?,
                    native_pages = ?,
                    error = NULL
                WHERE id = ?
                """,
                (
                    info.absolute_path,
                    info.file_name,
                    file_name_norm,
                    info.extension,
                    info.category,
                    info.folder_path,
                    info.file_size,
                    info.modified_ns,
                    file_hash,
                    now_iso(),
                    now_iso(),
                    len(chunks),
                    ocr_pages,
                    native_pages,
                    document_id,
                ),
            )

        else:
            cur = conn.execute(
                """
                INSERT INTO documents(
                    source_root,
                    absolute_path,
                    relative_path,
                    file_name,
                    file_name_norm,
                    extension,
                    category,
                    folder_path,
                    file_size,
                    modified_ns,
                    sha256,
                    status,
                    indexed_at,
                    updated_at,
                    chunk_count,
                    ocr_pages,
                    native_pages,
                    error
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    'indexed',
                    ?, ?,
                    ?, ?, ?,
                    NULL
                )
                """,
                (
                    info.source_root,
                    info.absolute_path,
                    info.relative_path,
                    info.file_name,
                    file_name_norm,
                    info.extension,
                    info.category,
                    info.folder_path,
                    info.file_size,
                    info.modified_ns,
                    file_hash,
                    now_iso(),
                    now_iso(),
                    len(chunks),
                    ocr_pages,
                    native_pages,
                ),
            )

            document_id = int(cur.lastrowid)

        new_chunk_ids = []

        for chunk in chunks:
            cur = conn.execute(
                """
                INSERT INTO chunks(
                    document_id,
                    page_no,
                    chunk_no,
                    extraction_mode,
                    content,
                    content_norm
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    chunk.page_no,
                    chunk.chunk_no,
                    chunk.extraction_mode,
                    chunk.content,
                    chunk.content_norm,
                ),
            )

            chunk_id = int(cur.lastrowid)

            conn.execute(
                """
                INSERT INTO chunks_fts(
                    rowid,
                    content,
                    content_norm,
                    file_name,
                    file_name_norm,
                    category
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    chunk.content,
                    chunk.content_norm,
                    info.file_name,
                    file_name_norm,
                    info.category,
                ),
            )

            new_chunk_ids.append(chunk_id)

        conn.commit()

    return (
        document_id,
        old_chunk_ids,
        new_chunk_ids,
    )


def fetch_chunks_by_ids(
    ids: Iterable[int],
) -> Dict[int, dict]:
    ids = list(
        dict.fromkeys(
            int(i)
            for i in ids
            if int(i) >= 0
        )
    )

    if not ids:
        return {}

    placeholders = ",".join(
        "?"
        for _ in ids
    )

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                c.id,
                c.document_id,
                c.page_no,
                c.chunk_no,
                c.extraction_mode,
                c.content,
                c.content_norm,

                d.file_name,
                d.file_name_norm,
                d.relative_path,
                d.category,
                d.folder_path,
                d.extension,
                d.absolute_path

            FROM chunks c
            JOIN documents d
              ON d.id = c.document_id

            WHERE c.id IN ({placeholders})
            """,
            ids,
        ).fetchall()

    return {
        int(row["id"]): dict(row)
        for row in rows
    }


def filter_chunk_ids(
    ids: Iterable[int],
    category: Optional[str] = None,
    folder_prefix: Optional[str] = None,
    extension: Optional[str] = None,
) -> List[int]:
    ids = list(
        dict.fromkeys(
            int(i)
            for i in ids
            if int(i) >= 0
        )
    )

    if not ids:
        return []

    placeholders = ",".join(
        "?"
        for _ in ids
    )

    where = [
        f"c.id IN ({placeholders})"
    ]
    params = list(ids)

    if category:
        where.append("d.category = ?")
        params.append(category)

    if folder_prefix:
        where.append("d.folder_path LIKE ?")
        params.append(
            folder_prefix.rstrip("/") + "%"
        )

    if extension:
        ext = extension.lower()

        if not ext.startswith("."):
            ext = "." + ext

        where.append("d.extension = ?")
        params.append(ext)

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id
            FROM chunks c
            JOIN documents d
              ON d.id = c.document_id
            WHERE {' AND '.join(where)}
            """,
            params,
        ).fetchall()

    allowed = {
        int(row["id"])
        for row in rows
    }

    return [
        i
        for i in ids
        if i in allowed
    ]


def _fts_escape_token(token: str) -> str:
    return token.replace('"', '""')


def lexical_search(
    query_norm: str,
    limit: int,
    phrase: bool = False,
    category: Optional[str] = None,
    folder_prefix: Optional[str] = None,
    extension: Optional[str] = None,
) -> List[int]:
    """
    FTS5/BM25:
    - filename được weight cao hơn content
    - query đã normalize bỏ dấu
    """
    tokens = [
        t
        for t in query_norm.split()
        if t
    ]

    if not tokens:
        return []

    if phrase:
        phrase_text = " ".join(tokens).replace('"', '""')
        match_expr = (
            f'file_name_norm:"{phrase_text}" '
            f'OR content_norm:"{phrase_text}"'
        )
    else:
        pieces = []

        for token in tokens:
            token = _fts_escape_token(token)

            pieces.extend(
                [
                    f'file_name_norm:"{token}"',
                    f'content_norm:"{token}"',
                ]
            )

        match_expr = " OR ".join(pieces)

    where = ["chunks_fts MATCH ?"]
    params = [match_expr]

    if category:
        where.append("d.category = ?")
        params.append(category)

    if folder_prefix:
        where.append("d.folder_path LIKE ?")
        params.append(
            folder_prefix.rstrip("/") + "%"
        )

    if extension:
        ext = extension.lower()
        if not ext.startswith("."):
            ext = "." + ext
        where.append("d.extension = ?")
        params.append(ext)

    params.append(int(limit))

    sql = f"""
        SELECT
            c.id,
            bm25(
                chunks_fts,
                1.0,
                1.2,
                4.0,
                6.0,
                0.3
            ) AS score

        FROM chunks_fts
        JOIN chunks c
          ON c.id = chunks_fts.rowid
        JOIN documents d
          ON d.id = c.document_id

        WHERE {' AND '.join(where)}

        ORDER BY score ASC
        LIMIT ?
    """

    try:
        with connect() as conn:
            rows = conn.execute(
                sql,
                params,
            ).fetchall()

        return [
            int(row["id"])
            for row in rows
        ]

    except sqlite3.OperationalError:
        return []


def get_all_chunks_for_dense():
    init_db()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.content,
                d.file_name,
                d.category
            FROM chunks c
            JOIN documents d
              ON d.id = c.document_id
            ORDER BY c.id
            """
        ).fetchall()

    return [
        (
            int(row["id"]),
            (
                f"Tên tài liệu: {row['file_name']}\n"
                f"Loại: {row['category']}\n"
                f"Nội dung: {row['content']}"
            ),
        )
        for row in rows
    ]


def get_all_chunks_for_typo():
    init_db()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.content_norm,
                d.file_name_norm,
                d.category
            FROM chunks c
            JOIN documents d
              ON d.id = c.document_id
            ORDER BY c.id
            """
        ).fetchall()

    results = []

    for row in rows:
        text = (
            f"{row['file_name_norm']} "
            f"{row['file_name_norm']} "
            f"{row['file_name_norm']} "
            f"{normalize_for_search(row['category'])} "
            f"{row['content_norm']}"
        )

        results.append(
            (
                int(row["id"]),
                text,
            )
        )

    return results



def list_filename_documents(
    category: Optional[str] = None,
    folder_prefix: Optional[str] = None,
    extension: Optional[str] = None,
):
    """
    Catalog filename ở cấp DOCUMENT, không phải chunk.
    Vì vậy cùng một file không bị lặp theo số chunk.
    """
    init_db()

    where = [
        "status = 'indexed'"
    ]
    params = []

    if category:
        where.append(
            "category = ?"
        )
        params.append(
            category
        )

    if folder_prefix:
        where.append(
            "folder_path LIKE ?"
        )
        params.append(
            folder_prefix.rstrip("/")
            + "%"
        )

    if extension:
        ext = extension.lower()

        if not ext.startswith("."):
            ext = "." + ext

        where.append(
            "extension = ?"
        )
        params.append(
            ext
        )

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                id,
                file_name,
                file_name_norm,
                relative_path,
                category,
                folder_path,
                extension
            FROM documents
            WHERE {' AND '.join(where)}
            ORDER BY file_name
            """,
            params,
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]

def get_stats(
    source_root: Optional[str] = None,
):
    init_db()

    where = ""
    params = []

    if source_root:
        where = "WHERE source_root = ?"
        params.append(source_root)

    with connect() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS documents,
                SUM(
                    CASE WHEN status = 'indexed'
                    THEN 1 ELSE 0 END
                ) AS indexed,
                SUM(
                    CASE WHEN status = 'error'
                    THEN 1 ELSE 0 END
                ) AS errors,
                COALESCE(SUM(chunk_count), 0) AS chunks,
                COALESCE(SUM(ocr_pages), 0) AS ocr_pages,
                COALESCE(SUM(native_pages), 0) AS native_pages
            FROM documents
            {where}
            """,
            params,
        ).fetchone()

        categories = conn.execute(
            f"""
            SELECT
                category,
                COUNT(*) AS count
            FROM documents
            {where}
            GROUP BY category
            ORDER BY category
            """,
            params,
        ).fetchall()

    return {
        "documents": int(row["documents"] or 0),
        "indexed": int(row["indexed"] or 0),
        "errors": int(row["errors"] or 0),
        "chunks": int(row["chunks"] or 0),
        "ocr_pages": int(row["ocr_pages"] or 0),
        "native_pages": int(row["native_pages"] or 0),
        "categories": [
            {
                "category": r["category"],
                "count": int(r["count"]),
            }
            for r in categories
        ],
    }


def list_documents(
    source_root: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    init_db()

    where = []
    params = []

    if source_root:
        where.append("source_root = ?")
        params.append(source_root)

    if category:
        where.append("category = ?")
        params.append(category)

    if status:
        where.append("status = ?")
        params.append(status)

    sql_where = (
        "WHERE " + " AND ".join(where)
        if where
        else ""
    )

    params.extend(
        [
            int(limit),
            int(offset),
        ]
    )

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                id,
                relative_path,
                file_name,
                extension,
                category,
                folder_path,
                status,
                chunk_count,
                ocr_pages,
                native_pages,
                error,
                indexed_at,
                updated_at
            FROM documents
            {sql_where}
            ORDER BY relative_path
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]
