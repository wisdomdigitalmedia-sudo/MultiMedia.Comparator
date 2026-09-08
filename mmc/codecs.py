"""Ranks and aliases for every commonly seen media codec / container."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CodecInfo:
    family: str
    label: str
    rank: float  # 0–100, higher is better quality potential
    lossless: bool = False
    kind: str = "video"  # video | audio | container


# Canonical family → info. Aliases map into family.
VIDEO_CODECS: dict[str, CodecInfo] = {
    "vvc": CodecInfo("vvc", "H.266 / VVC", 100),
    "av1": CodecInfo("av1", "AV1", 96),
    "hevc": CodecInfo("hevc", "H.265 / HEVC", 88),
    "vp9": CodecInfo("vp9", "VP9", 82),
    "prores": CodecInfo("prores", "Apple ProRes", 90, lossless=False),
    "dnxhd": CodecInfo("dnxhd", "DNxHD / DNxHR", 88),
    "ffv1": CodecInfo("ffv1", "FFV1", 94, lossless=True),
    "cineform": CodecInfo("cineform", "GoPro CineForm", 88),
    "h264": CodecInfo("h264", "H.264 / AVC", 70),
    "vc1": CodecInfo("vc1", "VC-1", 52),
    "vp8": CodecInfo("vp8", "VP8", 48),
    "mpeg4": CodecInfo("mpeg4", "MPEG-4 ASP", 40),
    "xvid": CodecInfo("xvid", "Xvid", 40),
    "divx": CodecInfo("divx", "DivX", 38),
    "theora": CodecInfo("theora", "Theora", 34),
    "mpeg2": CodecInfo("mpeg2", "MPEG-2", 32),
    "wmv": CodecInfo("wmv", "Windows Media Video", 28),
    "vp6": CodecInfo("vp6", "VP6", 26),
    "msmpeg4": CodecInfo("msmpeg4", "MS MPEG-4", 24),
    "mpeg1": CodecInfo("mpeg1", "MPEG-1", 20),
    "h263": CodecInfo("h263", "H.263", 22),
    "mjpeg": CodecInfo("mjpeg", "Motion JPEG", 30),
    "dv": CodecInfo("dv", "DV", 36),
    "jpeg2000": CodecInfo("jpeg2000", "JPEG 2000", 50),
    "huffyuv": CodecInfo("huffyuv", "HuffYUV", 80, lossless=True),
    "utvideo": CodecInfo("utvideo", "UT Video", 82, lossless=True),
    "rawvideo": CodecInfo("rawvideo", "Uncompressed video", 70, lossless=True),
    "svq": CodecInfo("svq", "Sorenson", 18),
    "rv": CodecInfo("rv", "RealVideo", 16),
    "cinepak": CodecInfo("cinepak", "Cinepak", 10),
    "indeo": CodecInfo("indeo", "Intel Indeo", 12),
    "flv1": CodecInfo("flv1", "Sorenson Spark / FLV1", 18),
    "unknown": CodecInfo("unknown", "Unknown video", 25),
}

AUDIO_CODECS: dict[str, CodecInfo] = {
    "truehd_atmos": CodecInfo("truehd_atmos", "TrueHD Atmos", 100, lossless=True, kind="audio"),
    "dtsx": CodecInfo("dtsx", "DTS:X", 97, lossless=True, kind="audio"),
    "dtshd_ma": CodecInfo("dtshd_ma", "DTS-HD MA", 94, lossless=True, kind="audio"),
    "truehd": CodecInfo("truehd", "Dolby TrueHD", 93, lossless=True, kind="audio"),
    "flac": CodecInfo("flac", "FLAC", 90, lossless=True, kind="audio"),
    "alac": CodecInfo("alac", "Apple Lossless", 88, lossless=True, kind="audio"),
    "pcm": CodecInfo("pcm", "PCM / WAV", 87, lossless=True, kind="audio"),
    "mlp": CodecInfo("mlp", "MLP", 92, lossless=True, kind="audio"),
    "ape": CodecInfo("ape", "Monkey's Audio", 86, lossless=True, kind="audio"),
    "wavpack": CodecInfo("wavpack", "WavPack", 86, lossless=True, kind="audio"),
    "tak": CodecInfo("tak", "TAK", 85, lossless=True, kind="audio"),
    "tta": CodecInfo("tta", "TTA", 84, lossless=True, kind="audio"),
    "wma_lossless": CodecInfo("wma_lossless", "WMA Lossless", 82, lossless=True, kind="audio"),
    "dtshd_hra": CodecInfo("dtshd_hra", "DTS-HD HRA", 78, kind="audio"),
    "dts": CodecInfo("dts", "DTS", 68, kind="audio"),
    "eac3_atmos": CodecInfo("eac3_atmos", "E-AC-3 Atmos (JOC)", 72, kind="audio"),
    "eac3": CodecInfo("eac3", "E-AC-3 / DD+", 62, kind="audio"),
    "ac3": CodecInfo("ac3", "AC-3 / DD", 54, kind="audio"),
    "opus": CodecInfo("opus", "Opus", 58, kind="audio"),
    "aac": CodecInfo("aac", "AAC", 50, kind="audio"),
    "vorbis": CodecInfo("vorbis", "Vorbis", 46, kind="audio"),
    "mp3": CodecInfo("mp3", "MP3", 36, kind="audio"),
    "mp2": CodecInfo("mp2", "MP2", 28, kind="audio"),
    "wma": CodecInfo("wma", "WMA", 30, kind="audio"),
    "ac4": CodecInfo("ac4", "AC-4", 66, kind="audio"),
    "atrac": CodecInfo("atrac", "ATRAC", 32, kind="audio"),
    "cook": CodecInfo("cook", "RealAudio Cook", 18, kind="audio"),
    "amr": CodecInfo("amr", "AMR", 12, kind="audio"),
    "unknown": CodecInfo("unknown", "Unknown audio", 20, kind="audio"),
}

CONTAINERS: dict[str, CodecInfo] = {
    "matroska": CodecInfo("matroska", "Matroska", 90, kind="container"),
    "mp4": CodecInfo("mp4", "MP4", 78, kind="container"),
    "mov": CodecInfo("mov", "QuickTime", 76, kind="container"),
    "webm": CodecInfo("webm", "WebM", 74, kind="container"),
    "m2ts": CodecInfo("m2ts", "BDAV / M2TS", 86, kind="container"),
    "mpegts": CodecInfo("mpegts", "MPEG-TS", 70, kind="container"),
    "avi": CodecInfo("avi", "AVI", 45, kind="container"),
    "mpeg": CodecInfo("mpeg", "MPEG program stream", 40, kind="container"),
    "wmv": CodecInfo("wmv", "ASF / WMV", 35, kind="container"),
    "flv": CodecInfo("flv", "Flash Video", 25, kind="container"),
    "ogg": CodecInfo("ogg", "Ogg", 50, kind="container"),
    "rm": CodecInfo("rm", "RealMedia", 15, kind="container"),
    "unknown": CodecInfo("unknown", "Unknown container", 40, kind="container"),
}

# ffprobe codec_name, fourcc, and filename tokens → family
_VIDEO_ALIASES: dict[str, str] = {
    "vvc": "vvc",
    "h266": "vvc",
    "h.266": "vvc",
    "av1": "av1",
    "av01": "av1",
    "libaom-av1": "av1",
    "hevc": "hevc",
    "h265": "hevc",
    "h.265": "hevc",
    "x265": "hevc",
    "hev1": "hevc",
    "hvc1": "hevc",
    "vp9": "vp9",
    "vp09": "vp9",
    "libvpx-vp9": "vp9",
    "prores": "prores",
    "apcn": "prores",
    "apch": "prores",
    "apcs": "prores",
    "apco": "prores",
    "ap4h": "prores",
    "dnxhd": "dnxhd",
    "dnxhr": "dnxhd",
    "ffv1": "ffv1",
    "cfhd": "cineform",
    "cineform": "cineform",
    "h264": "h264",
    "h.264": "h264",
    "x264": "h264",
    "avc": "h264",
    "avc1": "h264",
    "avc3": "h264",
    "libx264": "h264",
    "vc1": "vc1",
    "vc-1": "vc1",
    "wvc1": "vc1",
    "wmv3": "vc1",
    "vp8": "vp8",
    "libvpx": "vp8",
    "mpeg4": "mpeg4",
    "mp4v": "mpeg4",
    "fmp4": "mpeg4",
    "dx50": "divx",
    "divx": "divx",
    "div3": "divx",
    "div4": "divx",
    "div5": "divx",
    "xvid": "xvid",
    "theora": "theora",
    "mpeg2video": "mpeg2",
    "mpeg2": "mpeg2",
    "mpg2": "mpeg2",
    "mp2v": "mpeg2",
    "wmv1": "wmv",
    "wmv2": "wmv",
    "wmv": "wmv",
    "vp6": "vp6",
    "vp6f": "vp6",
    "vp6a": "vp6",
    "msmpeg4": "msmpeg4",
    "msmpeg4v1": "msmpeg4",
    "msmpeg4v2": "msmpeg4",
    "msmpeg4v3": "msmpeg4",
    "mpeg1video": "mpeg1",
    "mpeg1": "mpeg1",
    "mpg1": "mpeg1",
    "h263": "h263",
    "h263p": "h263",
    "h261": "h263",
    "mjpeg": "mjpeg",
    "mjpegb": "mjpeg",
    "dvvideo": "dv",
    "dv": "dv",
    "jpeg2000": "jpeg2000",
    "j2k": "jpeg2000",
    "huffyuv": "huffyuv",
    "ffvhuff": "huffyuv",
    "utvideo": "utvideo",
    "rawvideo": "rawvideo",
    "svq1": "svq",
    "svq3": "svq",
    "rv10": "rv",
    "rv20": "rv",
    "rv30": "rv",
    "rv40": "rv",
    "cinepak": "cinepak",
    "indeo2": "indeo",
    "indeo3": "indeo",
    "indeo4": "indeo",
    "indeo5": "indeo",
    "flv1": "flv1",
    "flv": "flv1",
}

_AUDIO_ALIASES: dict[str, str] = {
    "truehd": "truehd",
    "mlp": "mlp",
    "atmos": "truehd_atmos",
    "dts-hd ma": "dtshd_ma",
    "dts-hdma": "dtshd_ma",
    "dtshd_ma": "dtshd_ma",
    "dts-hd": "dtshd_hra",
    "dca": "dts",
    "dts": "dts",
    "dtsx": "dtsx",
    "dts:x": "dtsx",
    "flac": "flac",
    "alac": "alac",
    "pcm_s16le": "pcm",
    "pcm_s24le": "pcm",
    "pcm_s32le": "pcm",
    "pcm_f32le": "pcm",
    "pcm_bluray": "pcm",
    "pcm_dvd": "pcm",
    "pcm_s16be": "pcm",
    "pcm": "pcm",
    "wav": "pcm",
    "ape": "ape",
    "wavpack": "wavpack",
    "wv": "wavpack",
    "tak": "tak",
    "tta": "tta",
    "wmav1": "wma",
    "wmav2": "wma",
    "wmapro": "wma",
    "wmalossless": "wma_lossless",
    "wma": "wma",
    "eac3": "eac3",
    "eac3_atmos": "eac3_atmos",
    "ec-3": "eac3",
    "ddp": "eac3",
    "dd+": "eac3",
    "ac3": "ac3",
    "ac-3": "ac3",
    "dd": "ac3",
    "ac4": "ac4",
    "opus": "opus",
    "libopus": "opus",
    "aac": "aac",
    "mp4a": "aac",
    "vorbis": "vorbis",
    "mp3": "mp3",
    "mp2": "mp2",
    "mp2a": "mp2",
    "atrac3": "atrac",
    "atrac3p": "atrac",
    "atrac9": "atrac",
    "cook": "cook",
    "amr_nb": "amr",
    "amr_wb": "amr",
    "amr": "amr",
}

_CONTAINER_BY_EXT: dict[str, str] = {
    ".mkv": "matroska",
    ".mk3d": "matroska",
    ".mka": "matroska",
    ".webm": "webm",
    ".mp4": "mp4",
    ".m4v": "mp4",
    ".m4a": "mp4",
    ".m4b": "mp4",
    ".mov": "mov",
    ".qt": "mov",
    ".m2ts": "m2ts",
    ".mts": "m2ts",
    ".ts": "mpegts",
    ".m2t": "mpegts",
    ".avi": "avi",
    ".divx": "avi",
    ".mpg": "mpeg",
    ".mpeg": "mpeg",
    ".mpe": "mpeg",
    ".vob": "mpeg",
    ".evo": "mpeg",
    ".wmv": "wmv",
    ".asf": "wmv",
    ".flv": "flv",
    ".f4v": "flv",
    ".ogv": "ogg",
    ".ogg": "ogg",
    ".ogm": "ogg",
    ".rmvb": "rm",
    ".rm": "rm",
}


def _norm(name: str) -> str:
    return (
        (name or "")
        .strip()
        .lower()
        .replace("_", "-")
        .replace(" ", "")
        .replace(".", "")
    )


def resolve_video(name: str | None) -> CodecInfo:
    raw = (name or "").strip().lower()
    key = _norm(raw)
    # restore a couple of dotted forms after strip
    aliases = _VIDEO_ALIASES
    family = aliases.get(raw) or aliases.get(key)
    if not family:
        # try without punctuation
        compact = raw.replace(".", "").replace("-", "").replace(" ", "")
        family = aliases.get(compact)
    if not family:
        for token, fam in aliases.items():
            if token and token in raw:
                family = fam
                break
    return VIDEO_CODECS.get(family or "unknown", VIDEO_CODECS["unknown"])


def resolve_audio(name: str | None, atmos: bool = False) -> CodecInfo:
    raw = (name or "").strip().lower()
    key = raw.replace("_", "-")
    family = _AUDIO_ALIASES.get(raw) or _AUDIO_ALIASES.get(key)
    if not family:
        compact = raw.replace(".", "").replace("-", "").replace(" ", "")
        family = _AUDIO_ALIASES.get(compact)
    if not family:
        for token, fam in _AUDIO_ALIASES.items():
            if token and token in raw:
                family = fam
                break
    if atmos:
        if family in {"truehd", "mlp", None, "unknown"}:
            family = "truehd_atmos"
        elif family in {"eac3", "ac3"}:
            family = "eac3_atmos"
        elif family in {"dts", "dtshd_ma", "dtshd_hra"}:
            family = "dtsx"
    return AUDIO_CODECS.get(family or "unknown", AUDIO_CODECS["unknown"])


def resolve_container(ext: str | None, format_name: str | None = None) -> CodecInfo:
    ext = (ext or "").lower()
    if ext and not ext.startswith("."):
        ext = "." + ext
    family = _CONTAINER_BY_EXT.get(ext)
    if not family and format_name:
        fmt = format_name.lower()
        if "matroska" in fmt:
            family = "matroska"
        elif "webm" in fmt:
            family = "webm"
        elif "mp4" in fmt or "ismv" in fmt:
            family = "mp4"
        elif "mpegts" in fmt:
            family = "mpegts"
        elif "avi" in fmt:
            family = "avi"
        elif "asf" in fmt:
            family = "wmv"
    return CONTAINERS.get(family or "unknown", CONTAINERS["unknown"])


def video_rank(name: str | None) -> float:
    return resolve_video(name).rank


def audio_rank(name: str | None, atmos: bool = False) -> float:
    return resolve_audio(name, atmos=atmos).rank


def container_rank(ext: str | None, format_name: str | None = None) -> float:
    return resolve_container(ext, format_name).rank
