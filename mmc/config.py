"""Paths, extensions, ignore rules, and scoring weights."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "comparator.db"


def _catalog_search_paths() -> list[Path]:
    env = os.environ.get("MMC_CATALOG_DB") or os.environ.get("CATALOG_DB")
    home = Path.home()
    paths: list[Path] = []
    if env:
        paths.append(Path(env).expanduser())
    paths.extend(
        [
            DATA_DIR / "catalog.db",
            BASE_DIR / "media-host" / "data" / "catalog.db",
            # Legacy sibling folder from before the projects were merged
            BASE_DIR.parent / "Entertainment.Servers" / "data" / "catalog.db",
            home / "Entertainment.Servers" / "data" / "catalog.db",
        ]
    )
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


DEFAULT_CATALOG_PATHS = _catalog_search_paths()

HOST = "127.0.0.1"
PORT = 8767
SECRET_KEY = "multimedia-comparator-local-only"

# ---------------------------------------------------------------------------
# Containers / extensions — every common playable media type
# ---------------------------------------------------------------------------

VIDEO_EXTENSIONS = {
    ".mkv",
    ".mk3d",
    ".webm",
    ".mp4",
    ".m4v",
    ".mov",
    ".qt",
    ".avi",
    ".divx",
    ".mpg",
    ".mpeg",
    ".mpe",
    ".m2v",
    ".mpv",
    ".ts",
    ".m2ts",
    ".mts",
    ".m2t",
    ".tod",
    ".vob",
    ".evo",
    ".wmv",
    ".asf",
    ".flv",
    ".f4v",
    ".ogv",
    ".ogm",
    ".rmvb",
    ".rm",
    ".3gp",
    ".3g2",
    ".mxf",
    ".nut",
    ".wtv",
    ".dvr-ms",
    ".tp",
    ".trp",
    ".ifo",
}

AUDIO_EXTENSIONS = {
    ".mp3",
    ".mp2",
    ".mpa",
    ".flac",
    ".wav",
    ".wave",
    ".aiff",
    ".aif",
    ".aifc",
    ".alac",
    ".m4a",
    ".m4b",
    ".aac",
    ".ogg",
    ".oga",
    ".opus",
    ".wma",
    ".ape",
    ".wv",
    ".wavpack",
    ".tak",
    ".tta",
    ".ac3",
    ".eac3",
    ".ec3",
    ".dts",
    ".dtshd",
    ".dtsma",
    ".thd",
    ".truehd",
    ".mlp",
    ".mka",
    ".ra",
    ".ram",
    ".amr",
    ".awb",
    ".caf",
    ".au",
    ".snd",
    ".voc",
    ".spx",
    ".mpc",
    ".ofr",
    ".ofs",
    ".dsf",
    ".dff",
    ".w64",
    ".rf64",
}

MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

IGNORE_FOLDER_NAMES = {
    "sample",
    "samples",
    "proof",
    "proofs",
    "subs",
    "sub",
    "subtitles",
    "subtitle",
    "extras",
    "extra",
    "featurettes",
    "bonus",
    "trailers",
    "trailer",
    "screens",
    "screenshots",
    "covers",
    "cover",
    "artwork",
    "nfo",
    ".actors",
    "@eadir",
    "#recycle",
    "$recycle.bin",
    "system volume information",
}

IGNORE_EXTENSIONS = {
    ".nfo",
    ".sfv",
    ".srr",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".iso",
    ".img",
    ".bin",
    ".cue",
    ".torrent",
    ".url",
    ".lnk",
    ".db",
    ".ini",
    ".log",
    ".part",
    ".!qb",
    ".crdownload",
    ".idx",
    ".sub",
    ".srt",
    ".ass",
    ".ssa",
    ".sup",
    ".mks",
}

IGNORE_NAME_MARKERS = {
    ".sample.",
    "-sample.",
    ".sample-",
    "-sample-",
    "sample-",
    ".partial",
}

TV_LIBRARY_FOLDERS = {
    "tv shows",
    "tv show",
    "tv",
    "tvs",
    "television",
    "series",
    "shows",
    "anime",
    "cartoon",
    "cartoons",
    "kids tv",
    "kidstv",
    "docuseries",
}

MOVIE_LIBRARY_FOLDERS = {
    "movies",
    "movie",
    "films",
    "film",
    "video",
    "videos",
    "media",
    "downloads",
    "complete",
    "new",
    "mkv",
    "mp4",
    "cinema",
    "uhd movies",
    "4k movies",
    "uhd",
    "3d movies",
}

MUSIC_LIBRARY_FOLDERS = {
    "music",
    "mp3",
    "flac",
    "audio",
    "audios",
    "albums",
    "album",
    "songs",
    "song",
    "tracks",
    "discography",
    "lossless",
    "lossy",
    "cd",
    "cds",
    "vinyl",
    "artists",
    "artist",
}

# Generic dump / backup folders that are never a title
DUMP_FOLDER_NAMES = {
    "drive e backup",
    "drive f backup",
    "drive i backup",
    "backup from f",
    "backup",
    "backups",
    "movie directory the",
    "movie directory 0000",
    "movie directory a - b",
    "movie directory t - v",
    "movie directory w - z",
    "track videos",
}

# ---------------------------------------------------------------------------
# Scoring (sums conceptually to ~100 before penalties)
# ---------------------------------------------------------------------------

WEIGHTS = {
    "resolution": 28.0,
    "source": 18.0,
    "video_codec": 12.0,
    "hdr": 8.0,
    "audio": 12.0,
    "size": 10.0,
    "integrity": 6.0,
    "container": 2.0,
    "probe_bonus": 4.0,
}

PENALTY_3D = 8.0
PENALTY_INTERLACED = 4.0
PENALTY_UNREADABLE = 40.0
PENALTY_TINY = 25.0

# Expected bytes-per-minute by resolution bucket (encode, not remux)
BYTES_PER_MINUTE = {
    4320: 180_000_000,  # 8K
    2160: 90_000_000,
    1440: 45_000_000,
    1080: 28_000_000,
    720: 14_000_000,
    576: 8_000_000,
    480: 6_000_000,
    0: 4_000_000,
}

REMUX_SIZE_MULT = 2.4


def find_catalog_db(explicit: str | Path | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None
    for candidate in DEFAULT_CATALOG_PATHS:
        if candidate.is_file():
            return candidate
    return None
