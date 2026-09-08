"""Default configuration for Media Catalog."""

from pathlib import Path

# App data lives next to the project by default
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "catalog.db"

# Video extensions
VIDEO_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".m4v",
    ".avi",
    ".webm",
    ".mpg",
    ".mpeg",
}

# Audio extensions (MP3 / FLAC and common companions)
AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
    ".alac",
}

# All scanned media
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

# Folder name segments (case-insensitive) that exclude a path from results
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
    "@eadir",  # Synology
    "#recycle",
    "$recycle.bin",
    "system volume information",
}

# File extensions never treated as media (explicit denylist for clarity)
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
}

# Partial / incomplete download name markers
IGNORE_NAME_MARKERS = {
    ".sample.",
    "-sample.",
    ".sample-",
    "-sample-",
    "sample-",
    ".partial",
}

HOST = "127.0.0.1"
PORT = 8765
SECRET_KEY = "media-catalog-local-only-change-if-you-like"
