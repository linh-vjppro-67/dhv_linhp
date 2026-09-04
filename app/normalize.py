import re
import unicodedata


def display_nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def normalize_for_search(text: str) -> str:

    text = display_nfc(text).lower().strip()
    text = text.replace("đ", "d")

    text = unicodedata.normalize("NFD", text)
    text = "".join(
        ch
        for ch in text
        if unicodedata.category(ch) != "Mn"
    )

    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_display_text(text: str) -> str:
    text = display_nfc(text).replace("\u00a0", " ").replace("\x00", "")

    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)

    return "\n".join(lines).strip()


def query_tokens(query: str):
    return [
        t
        for t in normalize_for_search(query).split()
        if t
    ]


def looks_like_short_name_or_identifier(query: str) -> bool:
    tokens = query_tokens(query)
    if not tokens or len(tokens) > 5:
        return False

    return sum(len(t) >= 2 for t in tokens) >= max(1, len(tokens) - 1)
