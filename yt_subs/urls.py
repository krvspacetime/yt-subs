"""Small helpers for loading URL lists from plain-text files."""

from __future__ import annotations
from yt_subs.shared.models import UrlStr

from pathlib import Path


def load_urls_file(path: Path | str) -> list[UrlStr]:
    """Load URLs from a text file, one per line. Blank lines and # comments are skipped."""
    return [
        UrlStr(line.strip())
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
