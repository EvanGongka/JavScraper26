from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from javscraper.models import ScanEntry


VIDEO_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".f4v",
    ".flv",
    ".iso",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".rm",
    ".rmvb",
    ".ts",
    ".vob",
    ".webm",
    ".wmv",
}

NOISE_PATTERNS = [
    r"(144|240|360|480|720|1080)[Pp]",
    r"[24][Kk]",
    r"\[[^\]]+\]",
    r"\([^\)]+\)",
    r"\bHD\b",
    r"\bFHD\b",
    r"\b4K\b",
    r"\bUNCENSORED\b",
    r"\bSUB\b",
    r"\w+2048\.com",
]


def normalize_name(raw: str) -> str:
    value = raw.upper()
    for pattern in NOISE_PATTERNS:
        value = re.sub(pattern, " ", value, flags=re.IGNORECASE)
    value = value.replace(".", " ").replace("_", "-")
    return re.sub(r"\s+", " ", value).strip()


def extract_code_from_text(raw: str) -> str | None:
    text = normalize_name(raw)

    fc2_match = re.search(r"FC2[^A-Z0-9]{0,5}(?:PPV[^A-Z0-9]{0,5})?(\d{5,7})", text)
    if fc2_match:
        return f"FC2-{fc2_match.group(1)}"

    heydouga_match = re.search(r"HEYDOUGA[^A-Z0-9]{0,5}(\d{4})[-\s](\d{3,4}[A-Z]?)", text)
    if heydouga_match:
        return f"HEYDOUGA-{heydouga_match.group(1)}-{heydouga_match.group(2)}"

    separated = re.search(r"\b([A-Z]{2,10})[-\s](\d{2,6}[A-Z]?)\b", text)
    if separated:
        return f"{separated.group(1)}-{separated.group(2)}"

    compact = re.search(r"\b([A-Z]{2,10})(\d{2,6}[A-Z]?)\b", text)
    if compact:
        return f"{compact.group(1)}-{compact.group(2)}"

    uncensored = re.search(r"(?<!\d)(\d{6})[-_ ](\d{2,3})(?!\d)", text)
    if uncensored:
        return f"{uncensored.group(1)}-{uncensored.group(2)}"

    return None


def extract_code(path: Path) -> str | None:
    code = extract_code_from_text(path.stem)
    if code:
        return code
    if path.parent.name:
        return extract_code_from_text(path.parent.name)
    return None


def scan_directory(root: str | Path) -> tuple[list[ScanEntry], list[Path]]:
    root_path = Path(root)
    grouped: dict[str, list[Path]] = defaultdict(list)
    skipped: list[Path] = []

    for file_path in root_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        code = extract_code(file_path)
        if code:
            grouped[code].append(file_path)
        else:
            skipped.append(file_path)

    entries = [
        ScanEntry(code=code, files=sorted(paths))
        for code, paths in sorted(grouped.items())
    ]
    return entries, skipped
