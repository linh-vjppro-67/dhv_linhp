from pathlib import Path

from huggingface_hub import snapshot_download


root = Path(__file__).resolve().parent.parent
target = root / "models" / "qwen3-8b-4bit"
snapshot_download(
    repo_id="mlx-community/Qwen3-8B-4bit",
    local_dir=target,
)
print(f"Qwen chat model saved to: {target}")
