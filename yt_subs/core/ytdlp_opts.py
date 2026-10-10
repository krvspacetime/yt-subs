"""Shared yt-dlp option builders used by extractor and downloader."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from yt_dlp.cookies import SUPPORTED_BROWSERS, SUPPORTED_KEYRINGS

from yt_subs.error import YtSubsValueError
from yt_subs.shared.models import BrowserCookies, SubtitleFormat, VideoId

YOUTUBE_EXTRACTOR_ARGS: dict[str, dict[str, list[str]]] = {
    "youtube": {
        "skip": ["dash", "hls"],
        "player_client": ["android_vr"],
        "player_skip": ["configs", "js", "initial_data"],
    }
}

_COOKIE_SPEC_RE = re.compile(
    r"""(?x)
    (?P<browser>[^+:]+)
    (?:\s*\+\s*(?P<keyring>[^:]+))?
    (?:\s*:\s*(?!:)(?P<profile>.+?))?
    (?:\s*::\s*(?P<container>.+))?
    """
)


def normalize_cookies(cookies: str | None) -> BrowserCookies | None:
    if not cookies:
        return None

    match_ = _COOKIE_SPEC_RE.fullmatch(cookies.strip())
    if match_ is None:
        raise YtSubsValueError(
            f"invalid cookies spec: {cookies!r}. Expected BROWSER[+KEYRING]"
            "[:PROFILE][::CONTAINER], e.g. 'chrome' or 'firefox:myprofile'."
        )

    browser = match_.group("browser").strip().lower()
    keyring = match_.group("keyring")
    profile = match_.group("profile")
    container = match_.group("container")

    if browser not in SUPPORTED_BROWSERS:
        raise YtSubsValueError(
            f"unsupported browser: {browser!r}. Supported browsers are: "
            f"{', '.join(sorted(SUPPORTED_BROWSERS))}."
        )
    if keyring is not None:
        keyring = keyring.strip().upper()
        if keyring not in SUPPORTED_KEYRINGS:
            raise YtSubsValueError(
                f"unsupported keyring: {keyring!r}. Supported keyrings are: "
                f"{', '.join(sorted(SUPPORTED_KEYRINGS))}."
            )

    return browser, profile, keyring, container


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
    video_id: VideoId,
    subtitle_format: SubtitleFormat,
    resolved_langs: list[str],
    skip_video: bool,
    sleep_interval_subtitles: int,
    sleep_interval_requests: int,
    quiet: bool = True,
    cookies: BrowserCookies | None = None,
) -> dict[str, Any]:
    """Options for downloading subtitles (with or without video)."""
    opts: dict[str, Any] = {
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [*dict.fromkeys(resolved_langs)],
        "subtitlesformat": subtitle_format,
        "outtmpl": str(output_dir / f"{video_id}.%(ext)s"),
        "skip_download": skip_video,
        "sleep_interval_subtitles": sleep_interval_subtitles,
        "sleep_interval_requests": sleep_interval_requests,
        "socket_timeout": 30,
        "extractor_args": YOUTUBE_EXTRACTOR_ARGS,
        "noprogress": True,
    }

    if cookies is not None:
        opts["cookiesfrombrowser"] = cookies

    if quiet:
        opts["quiet"] = True
        opts["no_warnings"] = True

    if not skip_video:
        opts["format"] = "worst[ext=mp4]/worst"

    return opts
