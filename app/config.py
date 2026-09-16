from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("SMART_SEARCH_DATA_DIR", BASE_DIR / "data"))
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "search.db"
FAISS_PATH = DATA_DIR / "dense.faiss"

TYPO_VECTORIZER_PATH = DATA_DIR / "typo_vectorizer.joblib"
TYPO_MATRIX_PATH = DATA_DIR / "typo_matrix.npz"
TYPO_IDS_PATH = DATA_DIR / "typo_ids.npy"

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

# OCR
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "vie+eng")
OCR_DPI = int(os.getenv("OCR_DPI", "300"))
MIN_NATIVE_TEXT_CHARS = int(os.getenv("MIN_NATIVE_TEXT_CHARS", "80"))
OCR_IMAGE_TEXT_THRESHOLD = int(os.getenv("OCR_IMAGE_TEXT_THRESHOLD", "450"))
OCR_IMAGE_COVERAGE_THRESHOLD = float(
    os.getenv("OCR_IMAGE_COVERAGE_THRESHOLD", "0.65")
)
QUIET_TESSERACT = os.getenv("QUIET_TESSERACT", "true").lower() == "true"

# Chunking
CHUNK_SIZE_CHARS = int(os.getenv("CHUNK_SIZE_CHARS", "1500"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "220"))

# Search profile
SEARCH_PROFILE = os.getenv("SEARCH_PROFILE", "smart").lower()

if SEARCH_PROFILE == "light":
    EMBEDDING_MODEL = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    ENABLE_RERANKER = os.getenv("ENABLE_RERANKER", "false").lower() == "true"
else:
    EMBEDDING_MODEL = os.getenv(
        "EMBEDDING_MODEL",
        "BAAI/bge-m3",
    )
    ENABLE_RERANKER = os.getenv("ENABLE_RERANKER", "true").lower() == "true"

RERANKER_MODEL = os.getenv(
    "RERANKER_MODEL",
    "BAAI/bge-reranker-v2-m3",
)

MODEL_DEVICE = os.getenv("MODEL_DEVICE", "auto")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "12"))
EMBEDDING_MAX_SEQ_LENGTH = int(os.getenv("EMBEDDING_MAX_SEQ_LENGTH", "1024"))

RERANK_BATCH_SIZE = int(os.getenv("RERANK_BATCH_SIZE", "4"))
RERANK_MAX_LENGTH = int(os.getenv("RERANK_MAX_LENGTH", "1024"))
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "30"))

# Filename-first routing
FILENAME_FIRST_ENABLED = os.getenv(
    "FILENAME_FIRST_ENABLED",
    "true",
).lower() == "true"

FILENAME_ROUTE_MIN_SCORE = float(
    os.getenv("FILENAME_ROUTE_MIN_SCORE", "0.90")
)

FILENAME_SCORE_WINDOW = float(
    os.getenv("FILENAME_SCORE_WINDOW", "0.08")
)

FILENAME_MAX_RESULTS = int(
    os.getenv("FILENAME_MAX_RESULTS", "20")
)

FILENAME_AMBIGUOUS_LIMIT = int(
    os.getenv("FILENAME_AMBIGUOUS_LIMIT", "15")
)

# Retrieval
LEXICAL_LIMIT = int(os.getenv("LEXICAL_LIMIT", "100"))
TYPO_LIMIT = int(os.getenv("TYPO_LIMIT", "100"))
DENSE_LIMIT = int(os.getenv("DENSE_LIMIT", "100"))

RRF_K = int(os.getenv("RRF_K", "60"))
RRF_WEIGHT_EXACT = float(os.getenv("RRF_WEIGHT_EXACT", "2.0"))
RRF_WEIGHT_LEXICAL = float(os.getenv("RRF_WEIGHT_LEXICAL", "1.2"))
RRF_WEIGHT_TYPO = float(os.getenv("RRF_WEIGHT_TYPO", "1.4"))
RRF_WEIGHT_DENSE = float(os.getenv("RRF_WEIGHT_DENSE", "1.4"))

DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "3"))
MAX_TOP_K = int(os.getenv("MAX_TOP_K", "10"))

MIN_FINAL_SCORE = float(os.getenv("MIN_FINAL_SCORE", "0.0"))

# Sync
DEFAULT_WORKERS = int(
    os.getenv(
        "INDEX_WORKERS",
        str(max(1, min(4, (os.cpu_count() or 2) // 2))),
    )
)

CACHE_VERSION = 4

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
