from pathlib import Path
from typing import List

from .config import SUPPORTED_EXTENSIONS
from .normalize import display_nfc
from .types import FileInfo


def _display_rel_path(rel: Path) -> str:
    return "/".join(display_nfc(part) for part in rel.parts)


def discover_files(folder: str) -> List[FileInfo]:
    root = Path(folder).expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"Folder không tồn tại: {root}")

    if not root.is_dir():
        raise NotADirectoryError(str(root))

    results: List[FileInfo] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if path.name.startswith("~$"):
            continue

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        rel = path.relative_to(root)
        stat = path.stat()

        display_rel = _display_rel_path(rel)
        display_parts = display_rel.split("/")

        category = (
            display_parts[0]
            if len(display_parts) > 1
            else "(ROOT)"
        )

        folder_path = "/".join(display_parts[:-1])

        results.append(
            FileInfo(
                source_root=str(root),
                absolute_path=str(path.resolve()),
                relative_path=display_rel,
                file_name=display_nfc(path.name),
                extension=path.suffix.lower(),
                category=category,
                folder_path=folder_path,
                file_size=stat.st_size,
                modified_ns=stat.st_mtime_ns,
            )
        )

    return sorted(
        results,
        key=lambda x: x.relative_path.casefold(),
    )
