from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from typing import Iterable, Iterator, Unpack
from pathlib import Path

from yt_subs.error import ExtractorError, LanguageParseError

from yt_subs.core.resolver import resolve_subtitles, resolve_availability
from yt_subs.core import (
    extract_info,
    inspect_subtitle_availability,
    inspect_subtitles,
    download_subtitles,
)
from yt_subs.languages import LanguageSpec, LanguagesInput, parse_languages
from yt_subs.shared.models import (
    ResolvedSubtitle,
    SubtitleAvailability,
    SubtitleFile,
    LanguageMatch,
    SubtitleSourcePolicy,
    SubtitleResult,
    DownloadOverrides,
    DownloadStatus,
    UrlStr,
    VideoId,
    SubtitleFormat,
)


class YtSubs:
    __slots__ = (
        "languages",
        "output_dir",
        "subtitle_format",
        "skip_video",
        "sleep_interval_subtitles",
        "sleep_interval_requests",
        "language_match",
        "source_policy",
        "max_workers",
    )

    def __init__(
        self,
        *,
        languages: LanguagesInput | None = None,
        output_dir: Path | str | None = None,
        subtitle_format: SubtitleFormat | str | None = None,
        skip_video: bool | None = None,
        sleep_interval_subtitles: int | None = None,
        sleep_interval_requests: int | None = None,
        language_match: LanguageMatch | str | None = None,
        source_policy: SubtitleSourcePolicy | str | None = None,
        max_workers: int | None = None,
    ):
        self.languages = parse_languages(languages) if languages is not None else None
        self.output_dir = self._valid_output_dir(output_dir)
        self.subtitle_format = self._valid_sub_format(subtitle_format)
        self.skip_video = self._valid_skip_video(skip_video)
        self.sleep_interval_subtitles = self._valid_sleep_interval_subtitles(
            sleep_interval_subtitles
        )
        self.sleep_interval_requests = self._valid_sleep_interval_requests(
            sleep_interval_requests
        )
        self.language_match = self._valid_language_match(language_match)
        self.source_policy = self._valid_source_policy(source_policy)
        self.max_workers = self._valid_max_workers(max_workers)

    def _valid_output_dir(self, output_dir: Path | str | None) -> Path:
        if output_dir is None:
            return Path("yt_subs_downloads")
        if not isinstance(output_dir, Path):
            return Path(output_dir)
        return output_dir

    def _valid_sub_format(
        self, subtitle_format: SubtitleFormat | str | None
    ) -> SubtitleFormat:
        if subtitle_format is None:
            return SubtitleFormat.VTT

        if not isinstance(subtitle_format, SubtitleFormat):
            return SubtitleFormat(subtitle_format)
        return subtitle_format

    def _valid_skip_video(self, skip_video: bool | None) -> bool:
        if skip_video is None:
            return True
        return skip_video

    def _valid_sleep_interval_subtitles(
        self, sleep_interval_subtitles: int | None
    ) -> int:
        if sleep_interval_subtitles is None:
            return 2
        return sleep_interval_subtitles

    def _valid_sleep_interval_requests(
        self, sleep_interval_requests: int | None
    ) -> int:
        if sleep_interval_requests is None:
            return 1
        return sleep_interval_requests

    def _valid_language_match(
        self, language_match: LanguageMatch | str | None
    ) -> LanguageMatch:
        if language_match is None:
            return LanguageMatch.REGIONAL
        if isinstance(language_match, str):
            return LanguageMatch(language_match)
        return language_match

    def _valid_source_policy(
        self, source_policy: SubtitleSourcePolicy | str | None
    ) -> SubtitleSourcePolicy:
        if source_policy is None:
            return SubtitleSourcePolicy.MANUAL_THEN_AUTO
        if isinstance(source_policy, str):
            return SubtitleSourcePolicy(source_policy)
        return source_policy

    def _valid_max_workers(self, max_workers: int | None) -> int:
        if max_workers is None:
            return 1
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        return max_workers

    def _resolve_languages(
        self, languages: LanguagesInput | None
    ) -> tuple[LanguageSpec, ...]:
        if languages is None:
            if self.languages is None:
                raise LanguageParseError(
                    "No languages specified. You must provide languages in either "
                    "the YtSubs constructor or as an override."
                )
            return self.languages
        return parse_languages(languages)

    def inspect(self, url: str) -> SubtitleAvailability:
        info = extract_info(UrlStr(url))
        return inspect_subtitle_availability(UrlStr(url), info)

    def resolve(
        self,
        url: str,
        *,
        languages: LanguagesInput | None = None,
        language_match: LanguageMatch | str | None = None,
        source_policy: SubtitleSourcePolicy | str | None = None,
    ) -> tuple[ResolvedSubtitle, ...]:
        _langs = self._resolve_languages(languages)
        availability = self.inspect(url)
        return resolve_availability(
            availability,
            languages=_langs,
            language_match=(
                self.language_match
                if language_match is None
                else self._valid_language_match(language_match)
            ),
            source_policy=(
                self.source_policy
                if source_policy is None
                else self._valid_source_policy(source_policy)
            ),
        )

    def download(
        self,
        url: str,
        *,
        languages: LanguagesInput | None = None,
        output_dir: Path | str | None = None,
        subtitle_format: SubtitleFormat | None = None,
        skip_video: bool | None = None,
        sleep_interval_subtitles: int | None = None,
        sleep_interval_requests: int | None = None,
        language_match: LanguageMatch | str | None = None,
        source_policy: SubtitleSourcePolicy | str | None = None,
    ) -> SubtitleResult:
        _languages = self._resolve_languages(languages)
        _output_dir = (
            self.output_dir
            if output_dir is None
            else self._valid_output_dir(output_dir)
        )
        _subtitle_format = (
            self.subtitle_format
            if subtitle_format is None
            else self._valid_sub_format(subtitle_format)
        )
        _skip_video = (
            self.skip_video
            if skip_video is None
            else self._valid_skip_video(skip_video)
        )
        _sleep_interval_subtitles = (
            self.sleep_interval_subtitles
            if sleep_interval_subtitles is None
            else self._valid_sleep_interval_subtitles(sleep_interval_subtitles)
        )
        _sleep_interval_requests = (
            self.sleep_interval_requests
            if sleep_interval_requests is None
            else self._valid_sleep_interval_requests(sleep_interval_requests)
        )
        _language_match = (
            self.language_match
            if language_match is None
            else self._valid_language_match(language_match)
        )
        _source_policy = (
            self.source_policy
            if source_policy is None
            else self._valid_source_policy(source_policy)
        )

        info = extract_info(UrlStr(url))
        video_id: VideoId = info.get("id", "unknown")
        title = str(info.get("title", ""))

        manual, auto = inspect_subtitles(info)

        resolved = resolve_subtitles(
            _languages,
            frozenset(manual),
            frozenset(auto),
            _language_match,
            _source_policy,
        )

        downloaded = download_subtitles(
            UrlStr(url),
            resolved_langs=tuple(r for r in resolved if r.is_resolved),
            video_id=video_id,
            output_dir=_output_dir,
            sleep_interval_subtitles=_sleep_interval_subtitles,
            sleep_interval_requests=_sleep_interval_requests,
            subtitle_format=_subtitle_format,
            skip_video=_skip_video,
            info=info,
        )

        by_requested = {item.requested: item for item in downloaded}
        subtitles = []

        for spec in _languages:
            item = by_requested.get(spec.requested)
            if item is not None:
                subtitles.append(item)
            else:
                subtitles.append(
                    SubtitleFile(
                        requested=spec.requested,
                        resolved=None,
                        source=None,
                        status=DownloadStatus.UNAVAILABLE,
                        format=None,
                    )
                )

        return SubtitleResult(
            url=UrlStr(url),
            video_id=video_id,
            title=title,
            subtitles=tuple(subtitles),
        )

    def download_many(
        self,
        urls: Iterable[str],
        *,
        max_workers: int | None = None,
        **overrides: Unpack[DownloadOverrides],
    ) -> Iterator[SubtitleResult]:
        if isinstance(urls, str):
            raise TypeError("download_many() expects an iterable of URLs")
        workers = (
            self.max_workers
            if max_workers is None
            else self._valid_max_workers(max_workers)
        )

        if workers == 1:
            for url in urls:
                try:
                    yield self.download(url, **overrides)
                except ExtractorError as exc:
                    resolved_langs = self._resolve_languages(overrides.get("languages"))
                    subtitles = [
                        SubtitleFile(
                            requested=spec.requested,
                            resolved=None,
                            source=None,
                            status=DownloadStatus.ERROR,
                            error=str(exc),
                        )
                        for spec in resolved_langs
                    ]
                    yield SubtitleResult(
                        url=UrlStr(url),
                        video_id=VideoId("unknown"),
                        title="unknown",
                        subtitles=tuple(subtitles),
                    )
            return

        url_iter = iter(urls)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_url = {}

            for _ in range(workers):
                try:
                    url = next(url_iter)
                except StopIteration:
                    break
                f = executor.submit(self.download, url, **overrides)
                future_to_url[f] = url

            while future_to_url:
                done, _ = wait(future_to_url.keys(), return_when=FIRST_COMPLETED)

                for future in done:
                    url = future_to_url.pop(future)
                    try:
                        yield future.result()
                    except ExtractorError as exc:
                        resolved_langs = self._resolve_languages(
                            overrides.get("languages")
                        )
                        subtitles = [
                            SubtitleFile(
                                requested=spec.requested,
                                resolved=None,
                                source=None,
                                status=DownloadStatus.ERROR,
                                error=str(exc),
                            )
                            for spec in resolved_langs
                        ]
                        yield SubtitleResult(
                            url=UrlStr(url),
                            video_id=VideoId("unknown"),
                            title="unknown",
                            subtitles=tuple(subtitles),
                        )

                    try:
                        next_url = next(url_iter)
                    except StopIteration:
                        continue

                    f = executor.submit(self.download, next_url, **overrides)
                    future_to_url[f] = next_url
