"""Walk drive roots and collect video media, skipping junk."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from config import (
    AUDIO_EXTENSIONS,
    IGNORE_EXTENSIONS,
    IGNORE_FOLDER_NAMES,
    IGNORE_NAME_MARKERS,
    MEDIA_EXTENSIONS,
    VIDEO_EXTENSIONS,
)

# S01E02, 1x02, Season 1 Episode 2 style
EPISODE_RE = re.compile(
    r"(?:"
    r"[Ss](?P<s1>\d{1,2})\s*[Ee](?P<e1>\d{1,3})"
    r"|(?P<s2>\d{1,2})\s*[xX]\s*(?P<e2>\d{1,3})"
    r"|[Ss]eason\s*(?P<s3>\d{1,2}).*?[Ee]pisode\s*(?P<e3>\d{1,3})"
    r")",
    re.IGNORECASE,
)

# Strip common release noise from titles for display
RELEASE_NOISE_RE = re.compile(
    r"[\.\s_\-]+(?:"
    r"1080p|720p|2160p|4k|uhd|hdr|hdr10|dv|web[- ]?dl|webrip|bluray|blu[- ]?ray|"
    r"remux|x264|x265|h264|h265|hevc|avc|aac|dts|truehd|atmos|proper|repack|"
    r"internal|extended|theatrical|directors?\.?cut|unrated|multi|dual|subs?"
    r")(?=[\.\s_\-]|$)",
    re.IGNORECASE,
)

# Top-level library folders that mean "this tree is TV", not the show title
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

# Generic movie library folders (not a title)
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
}

# Generic music library folders (not an album title)
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

# Season / specials folder names — not show titles
SEASON_FOLDER_RE = re.compile(
    r"^(?:"
    r"season\s*\d{0,2}"
    r"|series\s*\d{0,2}"
    r"|specials?"
    r"|s\d{1,2}"
    r"|extras?"
    r")$",
    re.IGNORECASE,
)


def path_has_ignored_folder(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    for part in relative.parts[:-1]:  # exclude filename
        if part.lower() in IGNORE_FOLDER_NAMES:
            return True
        if part.startswith(".") and part not in (".", ".."):
            return True
    return False


def is_ignored_file(path: Path) -> bool:
    name_lower = path.name.lower()
    ext = path.suffix.lower()

    if ext in IGNORE_EXTENSIONS:
        return True
    if ext not in MEDIA_EXTENSIONS:
        return True
    if name_lower.startswith("."):
        return True
    for marker in IGNORE_NAME_MARKERS:
        if marker in name_lower:
            return True
    # standalone sample files often named Sample.mkv / sample-xxx.mkv
    stem = path.stem.lower()
    if stem in {"sample", "proof"} or stem.startswith("sample.") or stem.endswith(".sample"):
        return True
    return False


def clean_title(raw: str) -> str:
    # Dots/underscores to spaces, collapse whitespace
    text = raw.replace("_", " ").replace(".", " ")
    text = RELEASE_NOISE_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" -._")
    # Restore year in parentheses if pattern like "Movie 2020"
    text = re.sub(r"\b(19|20)\d{2}\b", lambda m: f"({m.group(0)})", text, count=1)
    # Fix double parens
    text = text.replace("((", "(").replace("))", ")")
    return text or raw


def _split_path_parts(relative_path: str | Path) -> list[str]:
    """Folder + file parts from a relative path (Windows or POSIX separators)."""
    text = str(relative_path).replace("\\", "/").strip("/")
    if not text:
        return []
    return [p for p in text.split("/") if p and p not in (".", "..")]


def under_tv_library(relative_path: str | Path) -> bool:
    """True if any path segment is a TV library folder (e.g. TV Shows)."""
    parts = _split_path_parts(relative_path)
    # folders only for library check (file name last)
    folders = parts[:-1] if len(parts) > 1 else parts
    return any(p.lower() in TV_LIBRARY_FOLDERS for p in folders)


def infer_show_name_from_path(
    relative_path: str | Path, file_stem: str, ep_match: re.Match | None
) -> str | None:
    """
    Show title from path, skipping library roots and Season folders.

    TV Shows/Survivor/S01E01.mkv          → Survivor
    TV Shows/Survivor/Season 01/ep.mkv    → Survivor
    Survivor/Season 01/ep.mkv             → Survivor
    """
    parts = _split_path_parts(relative_path)
    folders = parts[:-1]  # drop filename

    skip = TV_LIBRARY_FOLDERS | MOVIE_LIBRARY_FOLDERS | IGNORE_FOLDER_NAMES
    meaningful: list[str] = []
    for folder in folders:
        low = folder.lower()
        if low in skip:
            continue
        if SEASON_FOLDER_RE.match(folder):
            continue
        meaningful.append(folder)

    if meaningful:
        # Prefer first folder after library root (the show)
        return clean_title(meaningful[0])
    if ep_match:
        return clean_title(EPISODE_RE.sub(" ", file_stem))
    return None


def is_audio_ext(ext: str) -> bool:
    return (ext or "").lower() in AUDIO_EXTENSIONS


def is_video_ext(ext: str) -> bool:
    return (ext or "").lower() in VIDEO_EXTENSIONS


def under_music_library(relative_path: str | Path) -> bool:
    parts = _split_path_parts(relative_path)
    folders = parts[:-1] if len(parts) > 1 else parts
    return any(p.lower() in MUSIC_LIBRARY_FOLDERS for p in folders)


def infer_audio_display(relative_path: str | Path, file_name: str, stem: str) -> dict[str, Any]:
    """
    Audio: kind=audio. Prefer album folder as title context.
    Track file: "Album — Track Name" when nested under an album folder.
    """
    parts = _split_path_parts(relative_path)
    folders = parts[:-1]
    skip = (
        MUSIC_LIBRARY_FOLDERS
        | MOVIE_LIBRARY_FOLDERS
        | TV_LIBRARY_FOLDERS
        | IGNORE_FOLDER_NAMES
    )
    album = None
    for folder in reversed(folders):
        low = folder.lower()
        if low in skip or SEASON_FOLDER_RE.match(folder):
            continue
        # CD1 / Disc 2 are not albums
        if re.fullmatch(r"(cd|disc|disk|vinyl)\s*\d*", low):
            continue
        album = clean_title(folder)
        break

    track = clean_title(stem)
    # Strip leading track numbers: 01 - Title, 01. Title, 01 Title
    track = re.sub(r"^\d{1,3}(?:\s*[-._)\]]\s*|\s+)", "", track).strip() or clean_title(stem)

    if album and album.lower() != track.lower():
        display = f"{album} — {track}"
    elif album:
        display = album
    else:
        display = track

    return {
        "kind": "audio",
        "display_title": display,
        "show_name": album,  # reuse field as album name for sorting/export
        "season": None,
        "episode": None,
    }


def reclassify_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    Fix kind/show/title using relative_path / extension.

    Safe to run on agent results so the catalog PC gets correct types even if the
    Windows agent is still on an older scanner.py.
    """
    rel = item.get("relative_path") or item.get("file_path") or ""
    file_name = item.get("file_name") or Path(str(rel)).name
    stem = Path(file_name).stem
    ext = (item.get("extension") or Path(file_name).suffix or "").lower()
    if not ext.startswith(".") and ext:
        ext = "." + ext

    # Audio always wins over video heuristics
    if is_audio_ext(ext) or (
        not is_video_ext(ext)
        and under_music_library(rel)
        and ext in AUDIO_EXTENSIONS
    ):
        audio = infer_audio_display(rel, file_name, stem)
        item["kind"] = "audio"
        item["display_title"] = audio["display_title"]
        item["show_name"] = audio["show_name"]
        item["season"] = None
        item["episode"] = None
        item["extension"] = ext or item.get("extension")
        return item

    ep_match = EPISODE_RE.search(str(rel)) or EPISODE_RE.search(stem)
    is_tv = under_tv_library(rel) or bool(ep_match)

    if not is_tv:
        if item.get("kind") not in {"movie", "episode", "audio", "other"}:
            item["kind"] = "movie"
        return item

    # Don't reclassify pure audio as TV even if path has SxxExx in a weird folder
    if is_audio_ext(ext):
        return item

    season = item.get("season")
    episode = item.get("episode")
    if ep_match:
        groups = ep_match.groupdict()
        season = int(
            groups.get("s1") or groups.get("s2") or groups.get("s3") or 0
        )
        episode = int(
            groups.get("e1") or groups.get("e2") or groups.get("e3") or 0
        )

    show_name = infer_show_name_from_path(rel, stem, ep_match)
    # Never use "TV Shows" as the show title
    if show_name and show_name.lower() in TV_LIBRARY_FOLDERS:
        show_name = clean_title(EPISODE_RE.sub(" ", stem)) if ep_match else None

    item["kind"] = "episode"
    item["show_name"] = show_name
    item["season"] = season
    item["episode"] = episode

    if season is not None and episode is not None and (season or episode):
        ep_label = f"S{int(season):02d}E{int(episode):02d}"
        item["display_title"] = (
            f"{show_name} — {ep_label}" if show_name else ep_label
        )
    elif show_name:
        item["display_title"] = show_name
    # else keep existing display_title

    return item


def infer_display(path: Path, root: Path) -> dict[str, Any]:
    """
    Prefer parent folder as title when the file sits in a dedicated folder.
    Detect TV from SxxExx patterns and library folders named TV Shows / TV / etc.
    """
    file_name = path.name
    ext = path.suffix.lower()
    parent = path.parent
    parent_name = parent.name if parent != root else ""

    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    relative_path = str(rel)

    ep_match = EPISODE_RE.search(str(rel).replace("\\", "/"))
    is_tv_tree = under_tv_library(relative_path)
    kind = "other"
    show_name = None
    season = None
    episode = None
    display_title = clean_title(path.stem)

    if is_audio_ext(ext):
        audio = infer_audio_display(relative_path, file_name, path.stem)
        kind = "audio"
        display_title = audio["display_title"]
        show_name = audio["show_name"]
        season = None
        episode = None
    elif ep_match or is_tv_tree:
        kind = "episode"
        if ep_match:
            groups = ep_match.groupdict()
            season = int(
                groups.get("s1") or groups.get("s2") or groups.get("s3") or 0
            )
            episode = int(
                groups.get("e1") or groups.get("e2") or groups.get("e3") or 0
            )
        show_name = infer_show_name_from_path(relative_path, path.stem, ep_match)
        if show_name and show_name.lower() in TV_LIBRARY_FOLDERS:
            show_name = (
                clean_title(EPISODE_RE.sub(" ", path.stem)) if ep_match else None
            )
        if season is not None and episode is not None and (season or episode):
            ep_label = f"S{season:02d}E{episode:02d}"
            display_title = f"{show_name} — {ep_label}" if show_name else ep_label
        elif show_name:
            display_title = show_name
        else:
            display_title = clean_title(path.stem)
    else:
        # Movie: if parent is not root and looks like a title folder
        if (
            parent != root
            and parent_name
            and parent_name.lower() not in IGNORE_FOLDER_NAMES
        ):
            if parent_name.lower() not in MOVIE_LIBRARY_FOLDERS:
                display_title = clean_title(parent_name)
                kind = "movie"
            else:
                kind = "movie"
                display_title = clean_title(path.stem)
        else:
            kind = "movie"
            display_title = clean_title(path.stem)

    try:
        size_bytes = path.stat().st_size
    except OSError:
        size_bytes = 0

    return reclassify_item(
        {
            "file_path": str(path.resolve()),
            "relative_path": relative_path,
            "file_name": file_name,
            "display_title": display_title,
            "extension": ext,
            "size_bytes": size_bytes,
            "parent_folder": parent_name,
            "kind": kind,
            "show_name": show_name,
            "season": season,
            "episode": episode,
        }
    )


def normalize_windows_path_str(root_path: str | Path) -> str:
    """
    Normalize a Windows path string from the web UI / agent.

    Forms and HTML often mangle roots:
      'e' / 'E' / 'E:' / 'E:\\'  →  'E:/'
    """
    text = str(root_path).strip().strip('"').strip("'")
    text = text.replace("\\", "/")
    # Bare drive letter only (the bug: "Path is not a directory: e")
    if re.fullmatch(r"[A-Za-z]", text):
        return f"{text.upper()}:/"
    # E: or E:/
    if re.fullmatch(r"[A-Za-z]:/?", text):
        return f"{text[0].upper()}:/"
    # E:Movies (missing slash)
    m = re.fullmatch(r"([A-Za-z]):([^/].*)", text)
    if m:
        return f"{m.group(1).upper()}:/{m.group(2)}"
    # E:/something — normalize letter case
    m = re.match(r"^([A-Za-z]):/(.*)$", text)
    if m:
        rest = m.group(2)
        return f"{m.group(1).upper()}:/{rest}" if rest else f"{m.group(1).upper()}:/"
    return text


def normalize_scan_path(root_path: str | Path) -> Path:
    """
    Normalize user/agent paths so Windows drive roots work.

    HTML forms often turn 'D:\\' into 'D:' or even 'd'.
    On Windows, Path('D:') is *not* the drive root — it means the current
    directory on D:. Always expand bare drive letters to D:\\.
    """
    text = normalize_windows_path_str(root_path)
    # On Windows, Path prefers backslashes for drive roots
    if re.fullmatch(r"[A-Za-z]:/", text):
        text = f"{text[0]}:\\"
    elif re.match(r"^[A-Za-z]:/", text):
        text = text[0] + ":\\" + text[3:].replace("/", "\\")
    path = Path(text).expanduser()
    try:
        path = path.resolve()
    except OSError:
        pass
    return path


def scan_root(root_path: str | Path) -> list[dict[str, Any]]:
    root = normalize_scan_path(root_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Path is not a directory or not mounted: {root}")

    results: list[dict[str, Any]] = []
    # os.walk is efficient for large trees; prune ignored dirs in-place
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        # Prune ignored / hidden directories
        pruned = []
        for d in dirnames:
            low = d.lower()
            if low in IGNORE_FOLDER_NAMES or (d.startswith(".") and d not in (".", "..")):
                continue
            pruned.append(d)
        dirnames[:] = pruned

        current = Path(dirpath)
        if path_has_ignored_folder(current / "x", root):
            # safety if walk entered somehow
            dirnames[:] = []
            continue

        for name in filenames:
            path = current / name
            if is_ignored_file(path):
                continue
            if path_has_ignored_folder(path, root):
                continue
            try:
                results.append(infer_display(path, root))
            except OSError:
                continue

    results = [reclassify_item(r) for r in results]
    kind_order = {"movie": 0, "episode": 1, "audio": 2, "other": 3}

    def _sort_key(item: dict[str, Any]) -> tuple:
        return (
            kind_order.get(item.get("kind") or "other", 9),
            (item.get("display_title") or "").lower(),
            (item.get("show_name") or "").lower(),
            item.get("season") if item.get("season") is not None else -1,
            item.get("episode") if item.get("episode") is not None else -1,
            (item.get("file_name") or "").lower(),
        )

    results.sort(key=_sort_key)
    return results


def format_size(num: int) -> str:
    if num < 1024:
        return f"{num} B"
    for unit in ("KB", "MB", "GB", "TB"):
        num /= 1024.0
        if num < 1024:
            return f"{num:.1f} {unit}"
    return f"{num:.1f} PB"
