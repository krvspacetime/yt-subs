import pytest

from yt_subs.core.downloader import (
    download_subtitles,
    expected_subtitle_path,
    find_subtitle_file,
    safe_filename_component,
)
from yt_subs.error import SubtitleDownloadError
from yt_subs.shared.models import (
    DownloadStatus,
    LangCodeRequested,
    LangCodeResolved,
    ResolvedSubtitle,
    SubtitleFormat,
    SubtitleSource,
    UrlStr,
    VideoId,
)

VIDEO_ID = VideoId("abc123")
LANG = LangCodeResolved("en")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("abc123", "abc123"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("../../evil", "_.._evil"),
        ("..\\..\\evil", "_.._evil"),
        ("a/b", "a_b"),
        ("..", "unknown"),
        ("...", "unknown"),
        ("", "unknown"),
        ("CON", "unknown"),
        ("lpt1", "unknown"),
        ("hi:there", "hi_there"),
        (123, "123"),
    ],
)
def test_safe_filename_component(raw, expected):
    assert safe_filename_component(raw) == expected


def test_expected_subtitle_path_rejects_traversal(tmp_path):
    with pytest.raises(SubtitleDownloadError):
        expected_subtitle_path(tmp_path, VideoId("../evil"), LANG, SubtitleFormat.VTT)

    with pytest.raises(SubtitleDownloadError):
        expected_subtitle_path(
            tmp_path, VideoId("..\\..\\evil"), LANG, SubtitleFormat.VTT
        )

    dest = expected_subtitle_path(tmp_path, VideoId("ok..id"), LANG, SubtitleFormat.VTT)
    assert dest == tmp_path / "ok..id.en.vtt"
    assert dest.parent == tmp_path

    assert (
        expected_subtitle_path(tmp_path, VideoId(".."), LANG, SubtitleFormat.VTT)
        == tmp_path / "...en.vtt"
    )


def test_expected_subtitle_path_coerces_non_str_ids(tmp_path):
    dest = expected_subtitle_path(tmp_path, VideoId("123"), LANG, SubtitleFormat.VTT)
    assert dest == tmp_path / "123.en.vtt"


def test_find_subtitle_file_refuses_to_escape_output_dir(tmp_path):
    with pytest.raises(SubtitleDownloadError):
        find_subtitle_file(tmp_path, VideoId("../evil"), LANG, SubtitleFormat.VTT)

    dest = expected_subtitle_path(tmp_path, VIDEO_ID, LANG, SubtitleFormat.VTT)
    dest.write_bytes(b"WEBVTT")
    assert find_subtitle_file(tmp_path, VIDEO_ID, LANG, SubtitleFormat.VTT) == dest


def _resolved(
    land: LangCodeRequested = LangCodeRequested("en"),
) -> tuple[ResolvedSubtitle, ...]:
    return (
        ResolvedSubtitle(
            requested=land,
            resolved=LangCodeResolved(land),
            source=SubtitleSource.MANUAL,
        ),
    )


def test_download_sanitizes_unsafe_video_id(monkeypatch, tmp_path):
    import yt_subs.core.downloader as downloader

    monkeypatch.setattr(
        downloader,
        "_fetch_subtitle_bytes",
        lambda url, **kw: b"WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nhi\n",
    )

    info = {
        "id": "../../evil",
        "title": "t",
        "subtitles": {"en": [{"ext": "vtt", "url": "https://example.com/en.vtt"}]},
    }

    files = download_subtitles(
        UrlStr("https://www.youtube.com/watch?v=x"),
        resolved_langs=_resolved(),
        video_id=VideoId("../../evil"),
        output_dir=tmp_path,
        subtitle_format=SubtitleFormat.VTT,
        sleep_interval_subtitles=0,
        sleep_interval_requests=0,
        skip_video=True,
        info=info,
    )

    assert len(files) == 1
    assert files[0].status == DownloadStatus.OK
    sub_path = files[0].sub_path
    assert sub_path is not None
    assert sub_path.parent == tmp_path
    assert sub_path.exists()
    assert sub_path.read_bytes().startswith(b"WEBVTT")

    escaped = list((tmp_path.parent).glob("evil*"))
    assert escaped == []


def test_download_uses_sanitized_id_for_ytdlp_outtmpl(monkeypatch, tmp_path):
    captured = {}

    def fake_ytdlp(*args, **kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr("yt_subs.core.downloader._download_subtitles_ytdlp", fake_ytdlp)

    download_subtitles(
        UrlStr("https://www.youtube.com/watch?v=x"),
        resolved_langs=_resolved(),
        video_id=VideoId("../../evil"),
        output_dir=tmp_path,
        subtitle_format=SubtitleFormat.VTT,
        sleep_interval_subtitles=0,
        sleep_interval_requests=0,
        skip_video=False,
        info=None,
    )

    assert captured["video_id"] == VideoId("_.._evil")
