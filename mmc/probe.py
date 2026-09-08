"""Deep-scan a media file with ffprobe (preferred) or mediainfo."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StreamInfo:
    index: int = 0
    codec_type: str = ""
    codec_name: str = ""
    codec_long: str = ""
    width: int | None = None
    height: int | None = None
    pix_fmt: str | None = None
    profile: str | None = None
    bit_rate: int | None = None
    channels: int | None = None
    channel_layout: str | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None
    frame_rate: str | None = None
    language: str | None = None
    color_transfer: str | None = None
    color_primaries: str | None = None
    color_space: str | None = None
    field_order: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    side_data: list[str] = field(default_factory=list)


@dataclass
class ProbeResult:
    ok: bool
    tool: str
    path: str
    error: str = ""
    duration_s: float | None = None
    size_bytes: int | None = None
    bit_rate: int | None = None
    format_name: str | None = None
    format_long: str | None = None
    video: StreamInfo | None = None
    audio: StreamInfo | None = None
    videos: list[StreamInfo] = field(default_factory=list)
    audios: list[StreamInfo] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def hdr(self) -> str:
        v = self.video
        if not v:
            return "sdr"
        blob = " ".join(
            [
                v.color_transfer or "",
                v.color_primaries or "",
                v.profile or "",
                " ".join(v.side_data),
                json.dumps(v.tags).lower(),
            ]
        ).lower()
        if "dovi" in blob or "dolby vision" in blob or "dvhe" in blob or "dvh1" in blob:
            if "smpte2084" in blob or "hdr10" in blob:
                return "dv_hdr10"
            return "dv"
        if "hdr10+" in blob or "hdr10plus" in blob:
            return "hdr10plus"
        if "smpte2084" in blob or "pq" == (v.color_transfer or "").lower():
            return "hdr10"
        if "arib-std-b67" in blob or "hlg" in blob:
            return "hlg"
        return "sdr"

    @property
    def atmos(self) -> bool:
        for a in self.audios or ([self.audio] if self.audio else []):
            blob = " ".join(
                [a.codec_name, a.codec_long, a.profile or "", json.dumps(a.tags).lower()]
            ).lower()
            if "atmos" in blob or "joc" in blob:
                return True
        return False

    @property
    def interlaced(self) -> bool:
        fo = (self.video.field_order if self.video else "") or ""
        return fo.lower() in {"tt", "bb", "tb", "bt", "interlaced"}

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["hdr"] = self.hdr
        data["atmos"] = self.atmos
        data["interlaced"] = self.interlaced
        return data


def which_probe_tools() -> dict[str, str | None]:
    return {
        "ffprobe": shutil.which("ffprobe"),
        "ffmpeg": shutil.which("ffmpeg"),
        "mediainfo": shutil.which("mediainfo"),
    }


def _to_int(value: Any) -> int | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _stream_from_ffprobe(s: dict[str, Any]) -> StreamInfo:
    tags = {str(k).lower(): str(v) for k, v in (s.get("tags") or {}).items()}
    side = []
    for item in s.get("side_data_list") or []:
        if isinstance(item, dict):
            side.append(str(item.get("side_data_type") or item))
        else:
            side.append(str(item))
    depth = _to_int(s.get("bits_per_raw_sample") or s.get("bits_per_sample"))
    return StreamInfo(
        index=int(s.get("index") or 0),
        codec_type=str(s.get("codec_type") or ""),
        codec_name=str(s.get("codec_name") or ""),
        codec_long=str(s.get("codec_long_name") or ""),
        width=_to_int(s.get("width")),
        height=_to_int(s.get("height")),
        pix_fmt=s.get("pix_fmt"),
        profile=s.get("profile"),
        bit_rate=_to_int(s.get("bit_rate")),
        channels=_to_int(s.get("channels")),
        channel_layout=s.get("channel_layout"),
        sample_rate=_to_int(s.get("sample_rate")),
        bit_depth=depth,
        frame_rate=s.get("r_frame_rate") or s.get("avg_frame_rate"),
        language=tags.get("language"),
        color_transfer=s.get("color_transfer"),
        color_primaries=s.get("color_primaries"),
        color_space=s.get("color_space"),
        field_order=s.get("field_order"),
        tags=tags,
        side_data=side,
    )


def probe_ffprobe(path: str | Path, timeout: float = 45.0) -> ProbeResult:
    from mmc.ffprobe_install import FfprobeInstallError, ensure_ffprobe

    try:
        exe = ensure_ffprobe(force=False)
    except FfprobeInstallError as exc:
        return ProbeResult(ok=False, tool="ffprobe", path=str(path), error=str(exc))
    cmd = [
        exe,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return ProbeResult(ok=False, tool="ffprobe", path=str(path), error="ffprobe timed out")
    except OSError as exc:
        return ProbeResult(ok=False, tool="ffprobe", path=str(path), error=str(exc))
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ffprobe failed").strip()[:400]
        return ProbeResult(ok=False, tool="ffprobe", path=str(path), error=err)
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        return ProbeResult(ok=False, tool="ffprobe", path=str(path), error=f"bad json: {exc}")

    fmt = data.get("format") or {}
    videos: list[StreamInfo] = []
    audios: list[StreamInfo] = []
    for s in data.get("streams") or []:
        info = _stream_from_ffprobe(s)
        if info.codec_type == "video" and (info.codec_name or "") not in {"mjpeg", "png"}:
            videos.append(info)
        elif info.codec_type == "video" and not videos:
            videos.append(info)
        elif info.codec_type == "audio":
            audios.append(info)
    size = _to_int(fmt.get("size"))
    if size is None:
        try:
            size = Path(path).stat().st_size
        except OSError:
            size = None
    return ProbeResult(
        ok=True,
        tool="ffprobe",
        path=str(path),
        duration_s=_to_float(fmt.get("duration")),
        size_bytes=size,
        bit_rate=_to_int(fmt.get("bit_rate")),
        format_name=fmt.get("format_name"),
        format_long=fmt.get("format_long_name"),
        video=videos[0] if videos else None,
        audio=audios[0] if audios else None,
        videos=videos,
        audios=audios,
        raw={"format": {k: fmt.get(k) for k in ("format_name", "duration", "bit_rate", "size", "nb_streams")}},
    )


def probe_mediainfo(path: str | Path, timeout: float = 45.0) -> ProbeResult:
    exe = shutil.which("mediainfo")
    if not exe:
        return ProbeResult(ok=False, tool="mediainfo", path=str(path), error="mediainfo not installed")
    try:
        proc = subprocess.run(
            [exe, "--Output=JSON", str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return ProbeResult(ok=False, tool="mediainfo", path=str(path), error=str(exc))
    if proc.returncode != 0:
        return ProbeResult(
            ok=False,
            tool="mediainfo",
            path=str(path),
            error=(proc.stderr or "mediainfo failed").strip()[:400],
        )
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        return ProbeResult(ok=False, tool="mediainfo", path=str(path), error=f"bad json: {exc}")

    tracks = data.get("media", {}).get("track") or data.get("track") or []
    videos: list[StreamInfo] = []
    audios: list[StreamInfo] = []
    duration = None
    size = None
    bit_rate = None
    format_name = None
    for t in tracks:
        ttype = (t.get("@type") or t.get("type") or "").lower()
        if ttype == "general":
            duration = _to_float(t.get("Duration"))
            size = _to_int(t.get("FileSize"))
            bit_rate = _to_int(t.get("OverallBitRate"))
            format_name = t.get("Format")
            continue
        info = StreamInfo(
            codec_type="video" if ttype == "video" else "audio" if ttype == "audio" else ttype,
            codec_name=str(t.get("Format") or t.get("CodecID") or ""),
            codec_long=str(t.get("Format_Commercial_IfAny") or t.get("Format") or ""),
            width=_to_int(t.get("Width")),
            height=_to_int(t.get("Height")),
            profile=t.get("Format_Profile"),
            bit_rate=_to_int(t.get("BitRate")),
            channels=_to_int(t.get("Channels")),
            sample_rate=_to_int(t.get("SamplingRate")),
            bit_depth=_to_int(t.get("BitDepth")),
            frame_rate=str(t.get("FrameRate") or "") or None,
            language=t.get("Language"),
            color_transfer=t.get("transfer_characteristics") or t.get("HDR_Format"),
            color_primaries=t.get("colour_primaries"),
            field_order=t.get("ScanType"),
            tags={"hdr_format": str(t.get("HDR_Format") or "")},
        )
        if ttype == "video":
            videos.append(info)
        elif ttype == "audio":
            audios.append(info)
    return ProbeResult(
        ok=bool(videos or audios),
        tool="mediainfo",
        path=str(path),
        error="" if (videos or audios) else "no streams",
        duration_s=duration,
        size_bytes=size,
        bit_rate=bit_rate,
        format_name=format_name,
        video=videos[0] if videos else None,
        audio=audios[0] if audios else None,
        videos=videos,
        audios=audios,
        raw={},
    )


def probe_file(path: str | Path, timeout: float = 45.0) -> ProbeResult:
    """Probe a local file. ffprobe first, mediainfo fallback."""
    p = Path(path)
    if not p.is_file():
        return ProbeResult(ok=False, tool="none", path=str(path), error="file not found")
    result = probe_ffprobe(p, timeout=timeout)
    if result.ok:
        return result
    alt = probe_mediainfo(p, timeout=timeout)
    if alt.ok:
        return alt
    if result.error and not alt.error:
        return result
    return alt if alt.error else result


def probe_from_dict(data: dict[str, Any]) -> ProbeResult:
    """Rebuild a ProbeResult from agent / cached JSON."""
    def _s(d: dict[str, Any] | None) -> StreamInfo | None:
        if not d:
            return None
        return StreamInfo(
            index=int(d.get("index") or 0),
            codec_type=str(d.get("codec_type") or ""),
            codec_name=str(d.get("codec_name") or ""),
            codec_long=str(d.get("codec_long") or d.get("codec_long_name") or ""),
            width=_to_int(d.get("width")),
            height=_to_int(d.get("height")),
            pix_fmt=d.get("pix_fmt"),
            profile=d.get("profile"),
            bit_rate=_to_int(d.get("bit_rate")),
            channels=_to_int(d.get("channels")),
            channel_layout=d.get("channel_layout"),
            sample_rate=_to_int(d.get("sample_rate")),
            bit_depth=_to_int(d.get("bit_depth") or d.get("bits_per_raw_sample")),
            frame_rate=d.get("frame_rate") or d.get("r_frame_rate"),
            language=d.get("language"),
            color_transfer=d.get("color_transfer"),
            color_primaries=d.get("color_primaries"),
            color_space=d.get("color_space"),
            field_order=d.get("field_order"),
            tags=d.get("tags") or {},
            side_data=list(d.get("side_data") or d.get("side_data_list") or []),
        )

    videos = [_s(x) for x in (data.get("videos") or [])]
    videos = [v for v in videos if v]
    audios = [_s(x) for x in (data.get("audios") or [])]
    audios = [a for a in audios if a]
    video = _s(data.get("video")) or (videos[0] if videos else None)
    audio = _s(data.get("audio")) or (audios[0] if audios else None)
    return ProbeResult(
        ok=bool(data.get("ok", True)),
        tool=str(data.get("tool") or "agent"),
        path=str(data.get("path") or ""),
        error=str(data.get("error") or ""),
        duration_s=_to_float(data.get("duration_s") or data.get("duration")),
        size_bytes=_to_int(data.get("size_bytes") or data.get("size")),
        bit_rate=_to_int(data.get("bit_rate")),
        format_name=data.get("format_name"),
        format_long=data.get("format_long"),
        video=video,
        audio=audio,
        videos=videos,
        audios=audios,
        raw=data.get("raw") or {},
    )
