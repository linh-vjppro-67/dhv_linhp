import contextlib
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            block = f.read(block_size)
            if not block:
                break
            h.update(block)

    return h.hexdigest()


@contextlib.contextmanager
def suppress_native_stderr(enabled: bool = True):
    if not enabled:
        yield
        return

    saved_fd = None
    null_fd = None

    try:
        saved_fd = os.dup(2)
        null_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null_fd, 2)
        yield
    finally:
        if saved_fd is not None:
            os.dup2(saved_fd, 2)
            os.close(saved_fd)
        if null_fd is not None:
            os.close(null_fd)
