"""Score a media item and pick the best copy in a group."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from mmc.codecs import audio_rank, container_rank, video_rank
from mmc.config import (
    BYTES_PER_MINUTE,
    PENALTY_3D,
    PENALTY_INTERLACED,
    PENALTY_TINY,
    PENALTY_UNREADABLE,
    REMUX_SIZE_MULT,
    WEIGHTS,
)
from mmc.filename_meta import FilenameMeta, hdr_rank, parse_filename_meta, source_label
from mmc.probe import ProbeResult


@dataclass
class QualityScore:
    total: float
    breakdown: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    height: int | None = None
    width: int | None = None
    source: str = "unknown"
    video_codec: str | None = None
    audio_codec: str | None = None
    hdr: str = "sdr"
    channels: float | None = None
    duration_s: float | None = None
    probed: bool = False
    remux: bool = False
    is_3d: bool = False
    summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _resolution_points(height: int | None) -> float:
    if not height:
        return 18.0  # unknown — don't crush the score
    table = (
        (4320, 100.0),
        (2160, 96.0),
        (1440, 78.0),
        (1080, 70.0),
        (720, 42.0),
        (576, 22.0),
        (480, 16.0),
        (360, 10.0),
    )
    for thresh, pts in table:
        if height >= thresh - 8:
            return pts
    return 8.0


def _channel_bonus(channels: float | None) -> float:
    if not channels:
        return 0.0
    if channels >= 8:
        return 12.0
    if channels >= 6:
        return 8.0
    if channels >= 3:
        return 3.0
    if channels >= 2:
        return 0.0
    return -4.0


def _expected_bytes(height: int | None, duration_s: float | None, remux: bool) -> float | None:
    if not duration_s or duration_s < 30:
        return None
    bucket = 0
    for key in sorted(BYTES_PER_MINUTE, reverse=True):
        if key and height and height >= key - 8:
            bucket = key
            break
    bpm = BYTES_PER_MINUTE.get(bucket, BYTES_PER_MINUTE[0])
    if remux:
        bpm = int(bpm * REMUX_SIZE_MULT)
    return bpm * (duration_s / 60.0)


def _size_points(
    size_bytes: int | None,
    height: int | None,
    duration_s: float | None,
    remux: bool,
    source: str,
) -> tuple[float, str]:
    if not size_bytes or size_bytes <= 0:
        return 40.0, "size unknown"
    # Without duration, compare to typical feature-length encodes
    expected = _expected_bytes(height, duration_s, remux)
    if expected is None:
        minutes = 100.0
        expected = _expected_bytes(height or 1080, minutes * 60, remux) or float(size_bytes)
        # TV episodes are often 20–60 min; don't punish smaller files too hard
        if size_bytes < expected * 0.15 and (height or 0) >= 720:
            return 35.0, "small for claimed resolution"
        ratio = size_bytes / max(expected, 1)
        pts = _clamp(50 + (ratio - 1) * 25, 20, 100)
        return pts, f"{size_bytes / 1_000_000:.0f} MB vs typical"
    ratio = size_bytes / max(expected, 1)
    # Remux / bluray: bigger is usually better. Tiny 4K is suspicious.
    if ratio < 0.18:
        return 18.0, "far below expected bitrate (possible upscale / bad encode)"
    if ratio < 0.4:
        return 40.0, "below typical bitrate"
    if ratio < 0.8:
        return 65.0, "reasonable bitrate"
    if ratio < 1.6:
        return 88.0, "healthy bitrate"
    if ratio < 3.0:
        return 96.0 if remux or source in {"remux", "bluray", "uhd-bluray"} else 80.0, "large file"
    return 70.0, "very large (not always better)"


def score_item(
    item: dict[str, Any],
    probe: ProbeResult | None = None,
    filename_meta: FilenameMeta | None = None,
) -> QualityScore:
    """Combine filename tokens, size, and optional deep-probe into one score."""
    file_name = item.get("file_name") or ""
    rel = item.get("relative_path") or ""
    meta = filename_meta or parse_filename_meta(file_name, rel)
    size = int(item.get("size_bytes") or 0)
    kind = item.get("kind") or "movie"

    height = meta.height
    width = meta.width
    vcodec = meta.video_codec
    acodec = meta.audio_codec
    hdr = meta.hdr
    channels = meta.channels
    remux = meta.remux or meta.source == "remux"
    source = meta.source
    source_rank = meta.source_rank
    duration = None
    probed = False
    interlaced = False
    unreadable = False
    atmos = meta.atmos
    container_ext = item.get("extension") or ""

    if probe and probe.ok:
        probed = True
        if probe.video:
            height = probe.video.height or height
            width = probe.video.width or width
            if probe.video.codec_name:
                vcodec = probe.video.codec_name
            if probe.video.bit_depth and probe.video.bit_depth >= 10 and hdr == "sdr":
                pass
        if probe.audio:
            if probe.audio.codec_name:
                acodec = probe.audio.codec_name
            if probe.audio.channels:
                channels = float(probe.audio.channels)
        if probe.duration_s:
            duration = probe.duration_s
        if probe.size_bytes:
            size = probe.size_bytes
        hdr = probe.hdr or hdr
        atmos = probe.atmos or atmos
        interlaced = probe.interlaced
        if probe.format_name:
            container_ext = item.get("extension") or container_ext
    elif probe and not probe.ok and probe.tool != "none":
        unreadable = True

    reasons: list[str] = []
    breakdown: dict[str, float] = {}

    res_pts = _resolution_points(height)
    breakdown["resolution"] = res_pts / 100.0 * WEIGHTS["resolution"]
    if height:
        reasons.append(f"{width or '?'}x{height}" if width else f"{height}p")
    else:
        reasons.append("resolution unknown")

    breakdown["source"] = source_rank / 100.0 * WEIGHTS["source"]
    reasons.append(source_label(source))

    v_rank = video_rank(vcodec) if vcodec else 40.0
    breakdown["video_codec"] = v_rank / 100.0 * WEIGHTS["video_codec"]
    reasons.append(vcodec or "video codec unknown")

    breakdown["hdr"] = hdr_rank(hdr) / 100.0 * WEIGHTS["hdr"]
    if hdr and hdr != "sdr":
        reasons.append(hdr.upper().replace("_", " + "))

    a_rank = audio_rank(acodec, atmos=atmos) if (acodec or atmos) else 35.0
    a_rank = _clamp(a_rank + _channel_bonus(channels), 0, 100)
    breakdown["audio"] = a_rank / 100.0 * WEIGHTS["audio"]
    audio_bits = []
    if atmos:
        audio_bits.append("Atmos")
    if acodec:
        audio_bits.append(acodec)
    if channels:
        audio_bits.append(f"{channels:g}ch")
    if audio_bits:
        reasons.append(" ".join(audio_bits))

    size_pts, size_why = _size_points(size, height, duration, remux, source)
    breakdown["size"] = size_pts / 100.0 * WEIGHTS["size"]
    reasons.append(size_why)

    integrity = 80.0
    if kind in {"movie", "episode"} and size and size < 8_000_000:
        integrity = 15.0
        reasons.append("tiny file")
    if duration is not None and kind == "movie" and duration < 40 * 60 and size < 80_000_000:
        integrity = min(integrity, 35.0)
        reasons.append("short duration for a movie")
    if unreadable:
        integrity = 5.0
    breakdown["integrity"] = integrity / 100.0 * WEIGHTS["integrity"]

    c_rank = container_rank(container_ext)
    breakdown["container"] = c_rank / 100.0 * WEIGHTS["container"]

    breakdown["probe_bonus"] = WEIGHTS["probe_bonus"] if probed else 0.0
    if probed:
        reasons.append("deep-scanned")

    total = sum(breakdown.values())
    is_3d = bool(meta.is_3d or item.get("is_3d"))
    if is_3d:
        total -= PENALTY_3D
        breakdown["penalty_3d"] = -PENALTY_3D
        reasons.append("3D (penalized for best-overall)")
    if interlaced:
        total -= PENALTY_INTERLACED
        breakdown["penalty_interlaced"] = -PENALTY_INTERLACED
        reasons.append("interlaced")
    if unreadable:
        total -= PENALTY_UNREADABLE
        breakdown["penalty_unreadable"] = -PENALTY_UNREADABLE
    if size and size < 2_000_000 and kind != "audio":
        total -= PENALTY_TINY
        breakdown["penalty_tiny"] = -PENALTY_TINY

    total = round(_clamp(total, 0, 110), 2)
    res_txt = f"{height}p" if height else "res?"
    src_txt = source_label(source)
    codec_txt = vcodec or "?"
    summary = f"{res_txt} · {src_txt} · {codec_txt}"
    if hdr and hdr != "sdr":
        summary += f" · {hdr}"
    if atmos:
        summary += " · Atmos"

    return QualityScore(
        total=total,
        breakdown={k: round(v, 2) for k, v in breakdown.items()},
        reasons=reasons,
        height=height,
        width=width,
        source=source,
        video_codec=vcodec,
        audio_codec=acodec,
        hdr=hdr,
        channels=channels,
        duration_s=duration,
        probed=probed,
        remux=remux,
        is_3d=is_3d,
        summary=summary,
    )


def pick_winner(scored: list[tuple[dict[str, Any], QualityScore]]) -> int:
    """Index of the best copy. Tie-break: probed, then larger, then remux."""

    def key(pair: tuple[int, dict[str, Any], QualityScore]) -> tuple:
        i, item, score = pair
        return (
            score.total,
            1 if score.probed else 0,
            1 if score.remux else 0,
            int(item.get("size_bytes") or 0),
        )

    ranked = sorted(((i, it, sc) for i, (it, sc) in enumerate(scored)), key=key, reverse=True)
    return ranked[0][0] if ranked else 0
