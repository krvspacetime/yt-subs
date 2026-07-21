"""Shared yt-dlp option builders used by extractor and downloader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yt_subs.shared.models import SubtitleFormat

YOUTUBE_EXTRACTOR_ARGS: dict[str, dict[str, list[str]]] = {
    "youtube": {
        "skip": ["dash", "hls"],
        "player_client": ["android_vr"],
        "player_skip": ["configs", "js", "initial_data"],
    }
}


def base_extract_opts(**overrides: Any) -> dict[str, Any]:
    """Lightweight metadata extraction options."""
    return {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "extractor_args": YOUTUBE_EXTRACTOR_ARGS,
        **overrides,
    }


def subtitle_download_opts(
    *,
    output_dir: Path,
    subtitle_format: SubtitleFormat,
    resolved_langs: list[str],
    skip_video: bool,
    sleep_interval_subtitles: int,
    sleep_interval_requests: int,
    quiet: bool = True,
) -> dict[str, Any]:
    """Options for downloading subtitles (with or without video)."""
    opts: dict[str, Any] = {
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": resolved_langs,
        "subtitlesformat": subtitle_format,
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "skip_download": skip_video,
        "sleep_interval_subtitles": sleep_interval_subtitles,
        "sleep_interval_requests": sleep_interval_requests,
        "socket_timeout": 30,
        "extractor_args": YOUTUBE_EXTRACTOR_ARGS,
        "cookiesfrombrowser": ("chrome", None, None, None),
    }

    if quiet:
        opts["quiet"] = True
        opts["no_warnings"] = True

    if not skip_video:
        opts["format"] = "worst[ext=mp4]/worst"

    return opts
