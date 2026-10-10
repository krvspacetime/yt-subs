from __future__ import annotations

from yt_subs.shared.models import YtdlpVideoInfo

MOCK_VIDEO_INFO_OK: YtdlpVideoInfo = {
    "_type": "video",
    "id": "abc123",
    "extractor": "youtube",
    "title": "Mock Video Title",
    "subtitles": {
        "en": [
            {"ext": "vtt", "url": "https://example.com/en.vtt"},
            {"ext": "srt", "url": "https://example.com/en.srt"},
        ],
        "es": [
            {"ext": "vtt", "url": "https://example.com/es.vtt"},
        ],
    },
    "automatic_captions": {
        "en-orig": [
            {"ext": "vtt", "url": "https://example.com/en-orig.vtt"},
        ],
        "de": [
            {"ext": "vtt", "url": "https://example.com/de_auto.vtt"},
        ],
    },
}

MOCK_VIDEO_INFO_NO_SUBS: YtdlpVideoInfo = {
    "id": "xyz789",
    "title": "Mock Video No Subs",
    "subtitles": {},
    "automatic_captions": {},
}

MOCK_VTT_CONTENT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.000
>> SPEAKER: Hello world!

00:00:03.000 --> 00:00:06.000
[Music]
This is a test of the subtitle library.
"""

MOCK_SRT_CONTENT = """1
00:00:01,000 --> 00:00:03,000
>> SPEAKER: Hello world!

2
00:00:03,000 --> 00:00:06,000
[Music]
This is a test of the subtitle library.
"""
