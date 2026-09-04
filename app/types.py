from dataclasses import dataclass
from typing import Optional


@dataclass
class FileInfo:
    source_root: str
    absolute_path: str
    relative_path: str
    file_name: str
    extension: str
    category: str
    folder_path: str
    file_size: int
    modified_ns: int


@dataclass
class ExtractedUnit:
    text: str
    page_no: Optional[int]
    extraction_mode: str


@dataclass
class Chunk:
    content: str
    content_norm: str
    page_no: Optional[int]
    chunk_no: int
    extraction_mode: str
