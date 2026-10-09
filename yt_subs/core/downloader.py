from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import yt_dlp

from yt_subs.core.extractor import is_native_auto_caption_track
from yt_subs.core.ytdlp_opts import subtitle_download_opts
from yt_subs.shared.models import (
    DownloadStatus,
    ResolvedSubtitle,
    SubtitleFile,
    UrlStr,
    LangCodeResolved,
    SubtitleFormat,
    SubtitleSource,
    VideoId,
    YtdlpSanitizedInfo,
    BrowserCookies,
)
from yt_subs.error import SubtitleDownloadError

log = logging.getLogger(__name__)

_FETCH_USER_AGENT = "Mozilla/5.0 (compatible; yt-subs/0.1)"

_MAX_SUBTITLE_BYTES = 5 * 1024 * 1024

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.\-]")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def safe_filename_component(value: object) -> str:
    component = _UNSAFE_FILENAME_CHARS.sub("_", str(value)).strip(".-")
    if not component or component.upper() in _WINDOWS_RESERVED_NAMES:
        return "unknown"
    return component


def find_subtitle_file(
    output_dir: Path,
    video_id: VideoId,
    lang: LangCodeResolved,
    subtitle_format: SubtitleFormat,
) -> Path | None:
    expected = expected_subtitle_path(output_dir, video_id, lang, subtitle_format)
    if expected.exists():
        return expected

    log.warning("expected subtitle not found: %s. searching output dir ...", expected)
    expected_suffix = f"[{safe_filename_component(video_id)}].{lang}.{subtitle_format}"
    for f in output_dir.iterdir():
        if f.is_file() and f.name.endswith(expected_suffix):
            return f

    return None


def expected_subtitle_path(
    output_dir: Path,
    video_id: VideoId,
    lang: LangCodeResolved,
    subtitle_format: SubtitleFormat,
) -> Path:
    dest = output_dir / f"{video_id}.{lang}.{subtitle_format}"
    if dest.resolve().parent != output_dir.resolve():
        raise SubtitleDownloadError(
            f"refusing to write subtitle outside of {output_dir}: {video_id!r}"
        )
    return dest


def find_track_url(
    info: YtdlpSanitizedInfo,
    *,
    resolved: LangCodeResolved,
    source: SubtitleSource,
    subtitle_format: SubtitleFormat,
) -> str | None:
    """Return the direct download URL for a resolved subtitle track, if known."""
    pool_key = "subtitles" if source == SubtitleSource.MANUAL else "automatic_captions"
    tracks: list[dict[str, Any]] = info.get(pool_key, {}).get(resolved, [])

    for track in tracks:
        if track.get("ext") != subtitle_format:
            continue
        if source == SubtitleSource.AUTO and not is_native_auto_caption_track(track):
            continue
        url = track.get("url")
        if isinstance(url, str) and url:
            return url

    return None


def _strip_bom(payload: bytes) -> bytes:
    return payload[3:] if payload.startswith(b"\xef\xbb\xbf") else payload


def _looks_like_subtitle(payload: bytes, subtitle_format: SubtitleFormat) -> bool:
    head = _strip_bom(payload).lstrip()[:32]
    match subtitle_format:
        case SubtitleFormat.VTT:
            return head.startswith(b"WEBVTT")
        case SubtitleFormat.JSON3:
            return head.startswith(b"{")
        case SubtitleFormat.SRV1 | SubtitleFormat.SRV2 | SubtitleFormat.SRV3:
            return head.startswith(b"<?xml")
        case SubtitleFormat.TTML:
            return head.startswith(b"<?xml") or head.startswith(b"<tt")
        case SubtitleFormat.SRT:
            return re.match(rb"\d{1,6}\s", head) is not None
    return True


def _fetch_subtitle_bytes(
    url: str,
    *,
    subtitle_format: SubtitleFormat,
    timeout: int = 30,
    max_bytes: int = _MAX_SUBTITLE_BYTES,
) -> bytes:
    if urlsplit(url).scheme not in ("http", "https"):
        raise SubtitleDownloadError(f"refusing to fetch non-http subtitle url: {url!r}")

    request = Request(url, headers={"User-Agent": _FETCH_USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        payload = response.read(max_bytes + 1)

    if len(payload) > max_bytes:
        raise SubtitleDownloadError(
            f"subtitle response too large: over {max_bytes} bytes"
        )
    if payload.strip() and not _looks_like_subtitle(payload, subtitle_format):
        raise SubtitleDownloadError(
            f"subtitle response does not look like {subtitle_format}"
        )
    return payload


def _subtitle_file_from_path(
    item: ResolvedSubtitle,
    sub_path: Path,
    subtitle_format: SubtitleFormat,
) -> SubtitleFile:
    return SubtitleFile(
        requested=item.requested,
        resolved=item.resolved,
        source=item.source,
        status=DownloadStatus.OK,
        sub_path=sub_path,
        format=subtitle_format,
    )


def _missing_subtitle_file(item: ResolvedSubtitle) -> SubtitleFile:
    return SubtitleFile(
        requested=item.requested,
        resolved=item.resolved,
        source=item.source,
        status=DownloadStatus.MISSING,
    )


def _error_subtitle_file(item: ResolvedSubtitle, error: str) -> SubtitleFile:
    return SubtitleFile(
        requested=item.requested,
        resolved=item.resolved,
        source=item.source,
        status=DownloadStatus.ERROR,
        error=error,
    )


def _download_subtitles_direct(
    info: YtdlpSanitizedInfo,
    *,
    resolved_langs: tuple[ResolvedSubtitle, ...],
    video_id: VideoId,
    output_dir: Path,
    subtitle_format: SubtitleFormat,
    sleep_interval_subtitles: int,
) -> tuple[dict[LangCodeResolved, SubtitleFile], tuple[ResolvedSubtitle, ...]]:
    """Fetch subtitle files over HTTP using URLs from pre-extracted metadata."""
    results: dict[LangCodeResolved, SubtitleFile] = {}
    fallback_items: list[ResolvedSubtitle] = []

    for index, item in enumerate(resolved_langs):
        assert item.resolved is not None
        assert item.source is not None
        if index > 0 and sleep_interval_subtitles > 0:
            time.sleep(sleep_interval_subtitles)

        dest = expected_subtitle_path(
            output_dir, video_id, item.resolved, subtitle_format
        )
        track_url = find_track_url(
            info,
            resolved=item.resolved,
            source=item.source,
            subtitle_format=subtitle_format,
        )

        if track_url is None:
            log.warning(
                "  no direct URL for '%s' (%s, %s)",
                item.requested,
                item.resolved,
                item.source,
            )
            fallback_items.append(item)
            continue

        try:
            payload = _fetch_subtitle_bytes(track_url, subtitle_format=subtitle_format)
            if not payload.strip():
                log.warning(
                    "  empty response for '%s' (%s)",
                    item.requested,
                    item.resolved,
                )
                fallback_items.append(item)
                continue

            dest.write_bytes(payload)
            results[item.resolved] = _subtitle_file_from_path(
                item, dest, subtitle_format
            )
        except SubtitleDownloadError as exc:
            log.warning(
                "  rejected subtitle response for '%s' (%s): %s",
                item.requested,
                item.resolved,
                exc,
            )
            fallback_items.append(item)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            log.warning(
                "  direct fetch failed for '%s' (%s): %s",
                item.requested,
                item.resolved,
                exc,
            )
            fallback_items.append(item)

    return results, tuple(fallback_items)


def _download_subtitles_ytdlp(
    url: UrlStr,
    *,
    info: YtdlpSanitizedInfo | None,
    resolved_langs: tuple[ResolvedSubtitle, ...],
    video_id: VideoId,
    output_dir: Path,
    subtitle_format: SubtitleFormat,
    sleep_interval_subtitles: int,
    sleep_interval_requests: int,
    skip_video: bool,
    cookies: BrowserCookies | None = None,
) -> str | None:
    """Download subtitles via yt-dlp. Reuses pre-extracted info when provided."""
    opts = subtitle_download_opts(
        output_dir=output_dir,
        video_id=video_id,
        subtitle_format=subtitle_format,
        resolved_langs=[
            item.resolved for item in resolved_langs if item.resolved is not None
        ],
        skip_video=skip_video,
        sleep_interval_subtitles=sleep_interval_subtitles,
        sleep_interval_requests=sleep_interval_requests,
        cookies=cookies,
    )

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            if info is not None:
                ydl.process_ie_result(info, download=True)
            else:
                ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        log.error("yt-dlp download error: %s", exc)
        return str(exc)

    return None


def _collect_results_after_ytdlp(
    resolved_langs: tuple[ResolvedSubtitle, ...],
    *,
    video_id: VideoId,
    output_dir: Path,
    subtitle_format: SubtitleFormat,
    error: str | None,
) -> tuple[SubtitleFile, ...]:
    files: list[SubtitleFile] = []
    for item in resolved_langs:
        assert item.resolved is not None
        if error is not None:
            files.append(_error_subtitle_file(item, error))
            continue

        sub_path = find_subtitle_file(
            output_dir, video_id, item.resolved, subtitle_format
        )
        if sub_path is None:
            log.warning(
                "  '%s' (%s) — .%s not found after download",
                item.requested,
                item.resolved,
                subtitle_format,
            )
            files.append(_missing_subtitle_file(item))
            continue

        files.append(_subtitle_file_from_path(item, sub_path, subtitle_format))

    return tuple(files)


def download_subtitles(
    url: UrlStr,
    *,
    resolved_langs: tuple[ResolvedSubtitle, ...],
    video_id: VideoId,
    output_dir: Path,
    subtitle_format: SubtitleFormat,
    sleep_interval_subtitles: int,
    sleep_interval_requests: int,
    skip_video: bool,
    info: YtdlpSanitizedInfo | None = None,
    cookies: BrowserCookies | None = None,
) -> tuple[SubtitleFile, ...]:
    if not resolved_langs:
        return ()

    output_dir.mkdir(parents=True, exist_ok=True)

    safe_video_id = VideoId(safe_filename_component(video_id))

    log.info(
        "Downloading subtitles: %s",
        ", ".join(
            f"{item.requested}→{item.resolved}"
            if item.requested != item.resolved
            else str(item.requested)
            for item in resolved_langs
        ),
    )

    if info is not None and skip_video:
        direct_results, fallback_items = _download_subtitles_direct(
            info,
            resolved_langs=resolved_langs,
            video_id=safe_video_id,
            output_dir=output_dir,
            subtitle_format=subtitle_format,
            sleep_interval_subtitles=sleep_interval_subtitles,
        )

        if fallback_items:
            log.info(
                "Falling back to yt-dlp for %d subtitle(s)",
                len(fallback_items),
            )
            ytdlp_error = _download_subtitles_ytdlp(
                url,
                info=info,
                resolved_langs=fallback_items,
                video_id=safe_video_id,
                output_dir=output_dir,
                subtitle_format=subtitle_format,
                sleep_interval_subtitles=sleep_interval_subtitles,
                sleep_interval_requests=sleep_interval_requests,
                skip_video=True,
                cookies=cookies,
            )

            for item in fallback_items:
                assert item.resolved is not None
                if ytdlp_error is not None:
                    direct_results[item.resolved] = _error_subtitle_file(
                        item, ytdlp_error
                    )
                    continue

                sub_path = find_subtitle_file(
                    output_dir, safe_video_id, item.resolved, subtitle_format
                )
                if sub_path is None:
                    direct_results[item.resolved] = _missing_subtitle_file(item)
                else:
                    direct_results[item.resolved] = _subtitle_file_from_path(
                        item, sub_path, subtitle_format
                    )

        return tuple(
            direct_results[item.resolved]
            for item in resolved_langs
            if item.resolved is not None
        )

    ytdlp_error = _download_subtitles_ytdlp(
        url,
        info=info,
        resolved_langs=resolved_langs,
        video_id=safe_video_id,
        output_dir=output_dir,
        subtitle_format=subtitle_format,
        sleep_interval_subtitles=sleep_interval_subtitles,
        sleep_interval_requests=sleep_interval_requests,
        skip_video=skip_video,
        cookies=cookies,
    )
    return _collect_results_after_ytdlp(
        resolved_langs,
        video_id=safe_video_id,
        output_dir=output_dir,
        subtitle_format=subtitle_format,
        error=ytdlp_error,
    )
