"""Parse resolution, source, codecs, HDR, and audio from release names."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mmc.codecs import resolve_video


@dataclass
class FilenameMeta:
    height: int | None = None
    width: int | None = None
    source: str = "unknown"  # remux, bluray, webdl, webrip, hdtv, dvd, cam, ...
    source_rank: float = 20.0
    video_codec: str | None = None
    audio_codec: str | None = None
    atmos: bool = False
    channels: float | None = None
    hdr: str = "sdr"  # sdr, hdr10, hdr10plus, dv, dv_hdr10, hlg
    bit_depth: int | None = None
    is_3d: bool = False
    remux: bool = False
    release_group: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_RES_PATTERNS: list[tuple[re.Pattern[str], int, int | None]] = [
    (re.compile(r"\b4320p\b|\b8k\b", re.I), 4320, 7680),
    (re.compile(r"\b2160p\b|\b4k\b|\buhd\b", re.I), 2160, 3840),
    (re.compile(r"\b1440p\b|\bqhd\b", re.I), 1440, 2560),
    (re.compile(r"\b1080p\b|\b1080i\b|\bfhd\b", re.I), 1080, 1920),
    (re.compile(r"\b720p\b", re.I), 720, 1280),
    (re.compile(r"\b576p\b|\b576i\b", re.I), 576, 720),
    (re.compile(r"\b480p\b|\b480i\b", re.I), 480, 720),
    (re.compile(r"\b360p\b", re.I), 360, 640),
]

# Highest-first so remux / web-dl win over generic "web" or "bluray" in remux names
_SOURCE_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\bremux\b", re.I), "remux", 100.0),
    (re.compile(r"\buhd[\s._-]*blu-?ray\b|\bblu-?ray[\s._-]*uhd\b", re.I), "uhd-bluray", 90.0),
    (re.compile(r"\bbdmv\b", re.I), "bdmv", 88.0),
    (re.compile(r"\bblu-?ray\b|\bbluray\b|\bbb\b", re.I), "bluray", 82.0),
    (re.compile(r"\bhddvd\b|\bhd-dvd\b", re.I), "hddvd", 74.0),
    (re.compile(r"\bweb-?dl\b|\bwebdl\b", re.I), "webdl", 70.0),
    (re.compile(r"\bwebrip\b", re.I), "webrip", 58.0),
    (re.compile(r"\bweb\b", re.I), "web", 64.0),
    (re.compile(r"\bhdtv\b", re.I), "hdtv", 45.0),
    (re.compile(r"\bpdtv\b|\bdsr\b", re.I), "sdtv", 32.0),
    (re.compile(r"\bbdrip\b|\bbrrip\b", re.I), "bdrip", 60.0),
    (re.compile(r"\bhdrip\b", re.I), "hdrip", 30.0),
    (re.compile(r"\bdvdrip\b|\bdvd-?r\b|\bdvdscr\b|\bdvd\b", re.I), "dvd", 38.0),
    (re.compile(r"\bhdcam\b|\bcam\b|\btelesync\b|\btelecine\b|\bhdts\b|\bts\b|\btc\b|\br5\b", re.I), "cam", 8.0),
]

_VCODEC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bav1\b|\bav01\b", re.I), "av1"),
    (re.compile(r"\bx265\b|\bh[\s._-]?265\b|\bhevc\b", re.I), "hevc"),
    (re.compile(r"\bx264\b|\bh[\s._-]?264\b|\bavc\b", re.I), "h264"),
    (re.compile(r"\bvp9\b", re.I), "vp9"),
    (re.compile(r"\bxvid\b", re.I), "xvid"),
    (re.compile(r"\bdivx\b", re.I), "divx"),
    (re.compile(r"\bvc-?1\b", re.I), "vc1"),
    (re.compile(r"\bmpeg-?2\b|\bmpg2\b", re.I), "mpeg2"),
    (re.compile(r"\bvvc\b|\bh[\s._-]?266\b", re.I), "vvc"),
]

_ACODEC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\btruehd\b", re.I), "truehd"),
    (re.compile(r"\bdts-?hd[\s._-]?ma\b|\bdtsma\b", re.I), "dtshd_ma"),
    (re.compile(r"\bdts-?x\b|\bdtsx\b", re.I), "dtsx"),
    (re.compile(r"\bdts-?hd\b", re.I), "dtshd_hra"),
    (re.compile(r"\bdts\b", re.I), "dts"),
    (re.compile(r"\bflac\b", re.I), "flac"),
    (re.compile(r"\be-?ac-?3\b|\beac3\b|\bddp\b|\bdd\+", re.I), "eac3"),
    (re.compile(r"\bac-?3\b|\bdd5|\bdd[\s._-]?5", re.I), "ac3"),
    (re.compile(r"\baac\b", re.I), "aac"),
    (re.compile(r"\bopus\b", re.I), "opus"),
    (re.compile(r"\bmp3\b", re.I), "mp3"),
    (re.compile(r"\balac\b", re.I), "alac"),
    (re.compile(r"\blpcm\b|\bpcm\b", re.I), "pcm"),
]

_CHANNEL_RE = re.compile(r"\b(7[\s._-]?1|5[\s._-]?1|2[\s._-]?0|6[\s._-]?1|7[\s._-]?2)\b")
_GROUP_RE = re.compile(r"-([A-Za-z0-9]{2,24})$")


def parse_filename_meta(file_name: str, relative_path: str | None = None) -> FilenameMeta:
    blob = f"{relative_path or ''} {file_name}"
    stem = Path(file_name).stem
    meta = FilenameMeta()

    for rx, height, width in _RES_PATTERNS:
        if rx.search(blob):
            meta.height = height
            meta.width = width
            break

    for rx, name, rank in _SOURCE_PATTERNS:
        if rx.search(blob):
            meta.source = name
            meta.source_rank = rank
            break

    if re.search(r"\bremux\b", blob, re.I):
        meta.remux = True
        meta.source = "remux"
        meta.source_rank = 100.0

    for rx, codec in _VCODEC_PATTERNS:
        if rx.search(blob):
            meta.video_codec = resolve_video(codec).family
            break

    for rx, codec in _ACODEC_PATTERNS:
        if rx.search(blob):
            meta.audio_codec = codec
            break

    meta.atmos = bool(re.search(r"\batmos\b", blob, re.I))
    if re.search(r"\bdolby[\s._-]*vision\b|\bdovi\b|(?:^|[\s._-])dv(?:[\s._-]|$)", blob, re.I):
        if re.search(r"\bhdr10", blob, re.I):
            meta.hdr = "dv_hdr10"
        else:
            meta.hdr = "dv"
    elif re.search(r"\bhdr10\+", blob, re.I):
        meta.hdr = "hdr10plus"
    elif re.search(r"\bhdr10\b|\bhdr\b", blob, re.I):
        meta.hdr = "hdr10"
    elif re.search(r"\bhlg\b", blob, re.I):
        meta.hdr = "hlg"
    else:
        meta.hdr = "sdr"

    if re.search(r"\b10[\s._-]?bit\b|\bhi10p\b", blob, re.I):
        meta.bit_depth = 10
    elif re.search(r"\b8[\s._-]?bit\b", blob, re.I):
        meta.bit_depth = 8

    ch = _CHANNEL_RE.search(blob)
    if ch:
        token = re.sub(r"[\s._-]", ".", ch.group(1))
        try:
            meta.channels = float(token)
        except ValueError:
            meta.channels = None

    meta.is_3d = bool(
        re.search(r"(?:^|[\s._\-])(3d|hsbs|h-sbs|half-?sbs|hou|half-?ou)(?:[\s._\-]|$)", blob, re.I)
    )

    gm = _GROUP_RE.search(stem)
    if gm and not gm.group(1).isdigit():
        meta.release_group = gm.group(1)

    if not meta.video_codec:
        ext = Path(file_name).suffix.lower()
        if ext == ".avi":
            meta.video_codec = "xvid"
    return meta


def source_label(source: str) -> str:
    return {
        "remux": "Remux",
        "uhd-bluray": "UHD Blu-ray",
        "bdmv": "BDMV",
        "bluray": "Blu-ray",
        "hddvd": "HD DVD",
        "webdl": "WEB-DL",
        "webrip": "WEBRip",
        "web": "WEB",
        "hdtv": "HDTV",
        "sdtv": "SDTV",
        "bdrip": "BDRip",
        "hdrip": "HDRip",
        "dvd": "DVD",
        "cam": "CAM / TS",
        "unknown": "Unknown source",
    }.get(source, source)


def hdr_label(hdr: str) -> str:
    return {
        "dv_hdr10": "Dolby Vision + HDR10",
        "dv": "Dolby Vision",
        "hdr10plus": "HDR10+",
        "hdr10": "HDR10",
        "hlg": "HLG",
        "sdr": "SDR",
    }.get(hdr, hdr)


def hdr_rank(hdr: str) -> float:
    return {
        "dv_hdr10": 100.0,
        "dv": 90.0,
        "hdr10plus": 80.0,
        "hdr10": 70.0,
        "hlg": 40.0,
        "sdr": 0.0,
    }.get(hdr or "sdr", 0.0)
