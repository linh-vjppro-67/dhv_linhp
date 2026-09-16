__all__ = []
import os


# PyTorch and FAISS load separate OpenMP runtimes on macOS. Keeping inference
# single-threaded avoids a native crash when both are used in the same process.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
