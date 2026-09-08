"""Normalize titles and build duplicate-group keys from paths / names."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mmc.config import (
    DUMP_FOLDER_NAMES,
    IGNORE_FOLDER_NAMES,
    MOVIE_LIBRARY_FOLDERS,
    MUSIC_LIBRARY_FOLDERS,
    TV_LIBRARY_FOLDERS,
)

YEAR_RE = re.compile(r"(?:^|[\s._\-(\[])((?:19|20)\d{2})(?:[\s._\-\)\]]|$)")
# S01E02, S01.E02, 1x02, Season 1 Episode 2
EPISODE_RE = re.compile(
    r"(?:"
    r"[Ss](?P<s1>\d{1,2})\s*[._\-]?\s*[Ee](?P<e1>\d{1,3})"
    r"|(?P<s2>\d{1,2})\s*[xX]\s*(?P<e2>\d{1,3})"
    r"|[Ss]eason\s*(?P<s3>\d{1,2}).*?[Ee]pisode\s*(?P<e3>\d{1,3})"
    r")",
    re.IGNORECASE,
)
# Mini-series / anime style E01 or E08 without season
BARE_EP_RE = re.compile(r"(?:^|[\s._\-])[Ee](?P<e>\d{1,3})(?:[\s._\-]|$)")
# [HorribleSubs] One Piece - 851 [1080p]
ANIME_EP_RE = re.compile(
    r"^\[(?P<grp>[^\]]+)\]\s*(?P<show>.+?)\s+[-–]\s*(?P<ep>\d{1,4})\b"
)
# Serial chapter after the year: Chapter 02 of 15
SERIAL_CHAPTER_RE = re.compile(
    r"\bchapter\s*(\d{1,2})(?:\s*of\s*\d{1,2})?\b",
    re.I,
)
# Roman / numbered part suffix: Shada I, Part II
STORY_PART_RE = re.compile(
    r"(?:^|[\s._-])(?:part[\s._-]*)?(?P<part>I{1,3}|IV|VI{0,3}|V|\d{1,2})$",
    re.I,
)
# Daily shows: 2020.01.13 or 2020-01-13
DATE_RE = re.compile(
    r"(?P<y>(?:19|20)\d{2})[.\-_](?P<m>0[1-9]|1[0-2])[.\-_](?P<d>0[1-9]|[12]\d|3[01])"
)
# Multi-part disc (not "Part One" movies)
DISC_RE = re.compile(r"(?:^|[\s._\-])(?:cd|disc|disk)[\s._\-]*(\d{1,2})(?:[\s._\-]|$)", re.I)
# Scene/p2p group prefix: veto-john.wick.chapter.4.2023.
SCENE_PREFIX_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9]{1,14}-(?=[A-Za-z].{4,}\.(?:19|20)\d{2}[\s._\-])"
)
# Older avi scene: group-releasename (no dots)
HYPHEN_SCENE_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9]{1,14})-([A-Za-z0-9][A-Za-z0-9._]{2,})$"
)
# {edition-Director's Cut}
BRACE_EDITION_RE = re.compile(r"\{edition-([^}]+)\}", re.I)
# Trailing -GROUP
RELEASE_GROUP_RE = re.compile(r"-[A-Za-z0-9]{2,24}$")

SEASON_FOLDER_RE = re.compile(
    r"^(?:season\s*\d{0,2}|series\s*\d{0,2}|specials?|s\d{1,2}|extras?)$",
    re.I,
)

SEASON_PACK_RE = re.compile(
    r"[\s._\-]+(?:s\d{1,2}(?:[\s._\-]*[–\-e&][\s._\-]*s?\d{1,2})?|complete|season\s*\d+).*$",
    re.I,
)

# Short tokens MUST be whole words so "ts" does not eat "Secrets"
QUALITY_TOKEN_RE = re.compile(
    r"(?:"
    r"2160p|1440p|1080p|1080i|720p|576p|480p|360p|"
    r"\b(?:4k|8k|uhd|fhd|qhd)\b|"
    r"bluray|blu-?ray|bdrip|brrip|bdmv|remux|hddvd|hd-?dvd|"
    r"web-?dl|webrip|webdl|\bweb\b|hdtv|pdtv|\bdsr\b|dvdrip|dvd-?r|dvdscr|\bdvd\b|"
    r"hdrip|\bcam\b|telesync|telecine|hdcam|\br5\b|\btc\b|\bts\b|"
    r"\bamzn\b|\bnf\b|\bdsnp\b|\batvp\b|\bhulu\b|\bhmax\b|\bpcok\b|itunes|"
    r"x264|x265|h264|h265|h\s*264|h\s*265|hevc|\bavc\b|\bav1\b|xvid|divx|\bvp9\b|"
    r"10bit|10-bit|8bit|hi10p|hdr10\+|hdr10|\bhdr\b|dolby\s*vision|\bdovi\b|\bdv\b|\bhlg\b|\bsdr\b|"
    r"truehd|atmos|dts-?hd(?:[\s._-]?ma)?|\bdtsx\b|\bdts\b|eac3|dd\+|\bddp\b|\bdd\b|\bac3\b|\baac\b|"
    r"flac|opus|e-?ac-?3|7\.1|5\.1|2\.0|\bmp3\b|"
    r"repack|proper|internal|limited|readnfo|nuked|dirfix|nfofix|"
    r"\bmulti\b|dual[\s._-]?audio|\bsubs?\b|\bforced\b|"
    r"\b3d\b|hsbs|h-sbs|half-?sbs|\bhou\b|half-?ou|\bsbs\b|"
    r"remastered|\bhybrid\b|\bimax\b|open[\s._-]?matte|"
    r"extended(?:[\s._-]?cut)?|theatrical(?:[\s._-]?cut)?|"
    r"directors?\.?cut|unrated|final[\s._-]?cut|"
    r"rerip|internal"
    r")",
    re.I,
)

EDITION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"director'?s?[\s._-]*cut", re.I), "Director's Cut"),
    (re.compile(r"final[\s._-]*cut", re.I), "Final Cut"),
    (re.compile(r"legacy[\s._-]*cut", re.I), "Legacy Cut"),
    (re.compile(r"special[\s._-]*assembly", re.I), "Special Assembly"),
    (re.compile(r"ultimate[\s._-]*cut", re.I), "Ultimate Cut"),
    (re.compile(r"extended(?:[\s._-]*cut)?", re.I), "Extended"),
    (re.compile(r"theatrical(?:[\s._-]*cut)?", re.I), "Theatrical"),
    (re.compile(r"unrated", re.I), "Unrated"),
    (re.compile(r"criterion", re.I), "Criterion"),
    (re.compile(r"imax", re.I), "IMAX"),
    (re.compile(r"open[\s._-]*matte", re.I), "Open Matte"),
    (re.compile(r"grindhouse", re.I), "Grindhouse"),
    (re.compile(r"35mm", re.I), "35mm"),
]

_AFTER_YEAR_JUNK = {
    "ddp",
    "dd",
    "dts",
    "aac",
    "ac",
    "eac",
    "h",
    "x",
    "hdr",
    "sdr",
    "dv",
    "atmos",
    "truehd",
    "flac",
    "opus",
    "hevc",
    "avc",
    "web",
    "dl",
    "amzn",
    "nf",
    "multi",
    "repack",
    "proper",
    "internal",
    "remux",
    "bluray",
    "uhd",
    "ma",
    "hq",
}

SKIP_FOLDERS = (
    TV_LIBRARY_FOLDERS
    | MOVIE_LIBRARY_FOLDERS
    | MUSIC_LIBRARY_FOLDERS
    | IGNORE_FOLDER_NAMES
    | DUMP_FOLDER_NAMES
)


@dataclass
class Identity:
    kind: str  # movie | episode | audio | other
    key: str
    label: str
    title: str
    year: int | None = None
    show: str | None = None
    season: int | None = None
    episode: int | None = None
    air_date: str | None = None
    edition: str | None = None
    disc: int | None = None
    is_3d: bool = False
    extras: dict[str, Any] = field(default_factory=dict)
    show_year: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "label": self.label,
            "title": self.title,
            "year": self.year,
            "show": self.show,
            "season": self.season,
            "episode": self.episode,
            "air_date": self.air_date,
            "edition": self.edition,
            "disc": self.disc,
            "is_3d": self.is_3d,
        }


def split_path_parts(relative_path: str | Path | None) -> list[str]:
    text = str(relative_path or "").replace("\\", "/").strip("/")
    if not text:
        return []
    return [p for p in text.split("/") if p and p not in (".", "..")]


def normalize_title(text: str) -> str:
    t = (text or "").lower()
    t = t.replace("&", " and ")
    t = t.replace("+", " and ")
    t = t.replace("'", "").replace("’", "")
    t = t.replace("judgement", "judgment")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\bchapter\s+(\d+)\b", r"\1", t)
    t = re.sub(r"\bpt\s+(\d+)\b", r"part \1", t)
    t = re.sub(r"\bpart\s+(one|i)\b", "part 1", t)
    t = re.sub(r"\bpart\s+(two|ii)\b", "part 2", t)
    t = re.sub(r"\bpart\s+(three|iii)\b", "part 3", t)
    t = re.sub(r"\bpart\s+(four|iv)\b", "part 4", t)
    words = [w for w in t.split() if w]
    while words and words[0] in {"a", "an", "the"}:
        words.pop(0)
    return " ".join(words)


def _clean_spaces(text: str) -> str:
    text = text.replace("_", " ").replace(".", " ")
    text = re.sub(r"\s+", " ", text).strip(" -._")
    return text


def extract_year(text: str) -> tuple[int | None, str, str]:
    """Return (year, before, after) using the last plausible production year."""
    matches = list(YEAR_RE.finditer(text))
    if not matches:
        return None, text, ""
    # Prefer the last year that is not immediately after a resolution-like token
    chosen = matches[-1]
    if len(matches) > 1:
        # e.g. Band.Of.Brothers.2001.E08 — year is show year, keep it
        chosen = matches[0] if "e0" in text.lower() or "s0" in text.lower() else matches[-1]
        # Dated episodes handled separately
    year = int(chosen.group(1))
    return year, text[: chosen.start(1)], text[chosen.end(1) :]


def extract_edition(text: str) -> str | None:
    brace = BRACE_EDITION_RE.search(text)
    if brace:
        return _clean_spaces(brace.group(1))
    for pattern, label in EDITION_PATTERNS:
        if pattern.search(text):
            return label
    return None


def is_3d_name(text: str) -> bool:
    return bool(
        re.search(r"(?:^|[\s._\-])(3d|hsbs|h-sbs|half-?sbs|hou|half-?ou)(?:[\s._\-]|$)", text, re.I)
    )


def extract_disc(text: str) -> int | None:
    m = DISC_RE.search(text)
    return int(m.group(1)) if m else None


def strip_scene_prefix(stem: str) -> str:
    dotted = SCENE_PREFIX_RE.sub("", stem, count=1)
    if dotted != stem:
        return dotted
    # group-releasename (no dots): creep-bloodgames1080 → bloodgames1080
    if "." not in stem:
        m = HYPHEN_SCENE_RE.match(stem)
        if m and not YEAR_RE.search(m.group(1)):
            return m.group(2)
    return stem


def strip_release_group(stem: str) -> str:
    """Only strip -GROUP after a year or quality token (not group-title.avi)."""
    m = RELEASE_GROUP_RE.search(stem)
    if not m:
        return stem
    group = m.group(0)[1:]
    if group.isdigit():
        return stem
    head = stem[: m.start()]
    if not (
        YEAR_RE.search(head)
        or re.search(
            r"(?:2160p|1080p|720p|480p|bluray|web-?dl|webrip|hdtv|dvdrip|remux|x264|x265|h264|h265|hevc)$",
            head,
            re.I,
        )
    ):
        return stem
    return head


def strip_quality_tokens(text: str) -> str:
    cleaned = QUALITY_TOKEN_RE.sub(" ", text)
    cleaned = BRACE_EDITION_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned.replace(".", " ").replace("_", " "))
    return cleaned.strip(" -._")


def _folder_title_candidates(relative_path: str | Path | None) -> list[str]:
    parts = split_path_parts(relative_path)
    folders = parts[:-1]
    out: list[str] = []
    for folder in folders:
        low = folder.lower()
        if low in SKIP_FOLDERS:
            continue
        if SEASON_FOLDER_RE.match(folder):
            continue
        if re.fullmatch(r"(cd|disc|disk|vinyl)\s*\d*", low):
            continue
        cleaned = SEASON_PACK_RE.sub("", folder)
        cleaned = strip_quality_tokens(cleaned)
        cleaned = _clean_spaces(cleaned)
        if cleaned and cleaned.lower() not in SKIP_FOLDERS:
            out.append(cleaned)
    return out


def _parse_episode_ids(text: str) -> tuple[int | None, int | None]:
    m = EPISODE_RE.search(text)
    if not m:
        return None, None
    g = m.groupdict()
    season = int(g.get("s1") or g.get("s2") or g.get("s3") or 0)
    episode = int(g.get("e1") or g.get("e2") or g.get("e3") or 0)
    return season, episode


def _show_from_filename(stem: str) -> str:
    text = strip_scene_prefix(stem)
    # Cut at episode / date / year / quality
    cut = len(text)
    for rx in (EPISODE_RE, DATE_RE, BARE_EP_RE, YEAR_RE):
        m = rx.search(text)
        if m:
            cut = min(cut, m.start())
    qm = QUALITY_TOKEN_RE.search(text)
    if qm:
        cut = min(cut, qm.start())
    raw = strip_quality_tokens(text[:cut])
    return _clean_spaces(raw)


def movie_identity(
    file_name: str,
    relative_path: str | None = None,
    display_title: str | None = None,
) -> Identity:
    stem = Path(file_name).stem
    stem = strip_scene_prefix(stem)
    stem = strip_release_group(stem)
    edition = extract_edition(stem)
    is_3d = is_3d_name(stem) or is_3d_name(file_name)
    disc = extract_disc(stem) or extract_disc(relative_path or "")

    year, before, after = extract_year(stem)
    # Trailing 1080/720 glued to old scene names: bloodgames1080
    if not year:
        stem = re.sub(r"(?<!\d)(2160|1080|720|480)$", "", stem)
    title_raw = strip_quality_tokens(before if year else stem)
    title_raw = _clean_spaces(title_raw)
    # "Abbott and Costello - 1941 - Hold That Ghost" — title continues after year
    if year and after:
        tail = strip_quality_tokens(after)
        tail = re.sub(
            r"\b(directors? cut|theatrical|extended|unrated|final cut|legacy cut|"
            r"special assembly|remastered|internal|proper|repack|limited|3d|"
            r"cut|edition|criterion|collection)\b",
            " ",
            tail,
            flags=re.I,
        )
        tail = _clean_spaces(tail)
        tail_words = [
            w
            for w in normalize_title(tail).split()
            if w not in _AFTER_YEAR_JUNK and not re.fullmatch(r"\d+", w)
        ]
        if len(tail_words) >= 2 or (len(tail_words) == 1 and len(tail_words[0]) >= 6):
            title_raw = _clean_spaces(f"{title_raw} {tail}")
    # Serial chapters live after the year — keep them distinct
    chapter = None
    ch_m = SERIAL_CHAPTER_RE.search(after) if year else SERIAL_CHAPTER_RE.search(stem)
    if ch_m:
        chapter = int(ch_m.group(1))
        disc = disc or chapter
    if not title_raw or len(title_raw) < 2:
        folders = _folder_title_candidates(relative_path)
        if folders:
            year2, fbefore, _ = extract_year(folders[0])
            title_raw = strip_quality_tokens(fbefore if year2 else folders[0])
            title_raw = _clean_spaces(title_raw)
            year = year or year2
    if (not title_raw or len(title_raw) < 2) and display_title:
        title_raw = strip_quality_tokens(display_title)
        title_raw = _clean_spaces(title_raw)

    title_norm = normalize_title(title_raw)
    # Drop leftover edition words from the identity title
    title_norm = re.sub(
        r"\b(directors? cut|theatrical|extended|unrated|final cut|legacy cut|"
        r"special assembly|remastered|internal|proper|repack|limited|3d)\b",
        " ",
        title_norm,
    )
    title_norm = re.sub(r"\s+", " ", title_norm).strip()

    key_title = title_norm or "unknown"
    year_part = str(year) if year else "noyear"
    disc_part = f"|cd{disc}" if disc else ""
    key = f"movie|{key_title}|{year_part}{disc_part}"
    label = title_raw or file_name
    if year:
        label = f"{label} ({year})"
    if edition:
        label = f"{label} [{edition}]"
    return Identity(
        kind="movie",
        key=key,
        label=label,
        title=title_raw or key_title,
        year=year,
        edition=edition,
        disc=disc,
        is_3d=is_3d,
    )


def episode_identity(
    file_name: str,
    relative_path: str | None = None,
    show_name: str | None = None,
    season: int | None = None,
    episode: int | None = None,
) -> Identity:
    stem = Path(file_name).stem
    blob = f"{relative_path or ''} {file_name}"
    date_m = DATE_RE.search(stem) or DATE_RE.search(blob)
    anime = ANIME_EP_RE.match(stem.strip())
    s, e = _parse_episode_ids(stem)
    if s is None:
        s, e = _parse_episode_ids(blob)
    if anime and e is None:
        e = int(anime.group("ep"))
        s = 1
    # Catalog season/episode is a last resort and often wrong on dump folders
    if s is None and season not in (None, 0) and 1 <= int(season) <= 40:
        s = int(season)
    if e is None and episode not in (None, 0) and 1 <= int(episode) <= 80:
        e = int(episode)
    if e is None:
        bare = BARE_EP_RE.search(stem)
        if bare:
            e = int(bare.group("e"))
            # Season from a lone S07. sitting nearby, else leave unknown (not force 1)
            sm = re.search(r"(?:^|[\s._\-])[Ss](\d{1,2})(?:[\s._\-]|$)", stem)
            s = int(sm.group(1)) if sm else s

    folders = _folder_title_candidates(relative_path)
    show_raw = ""
    if anime:
        show_raw = _clean_spaces(anime.group("show"))
    if folders:
        show_raw = show_raw or folders[0]
    fn_show = _show_from_filename(stem)
    # Prefer folder show when filename show is empty / looks like quality leftovers
    if not show_raw:
        show_raw = fn_show
    elif fn_show and len(fn_show) > 2:
        # filename show is usually better if it isn't a dump name
        if normalize_title(fn_show) not in {
            normalize_title(x) for x in DUMP_FOLDER_NAMES
        }:
            show_raw = fn_show
    if show_name and (not show_raw or normalize_title(show_raw) in DUMP_FOLDER_NAMES):
        show_raw = strip_quality_tokens(show_name)

    show_raw = SEASON_PACK_RE.sub("", show_raw)
    show_raw = _clean_spaces(strip_quality_tokens(show_raw))
    show_norm = normalize_title(show_raw) or "unknown"

    show_year, _, _ = extract_year(stem)
    if date_m and e is None:
        air = f"{date_m.group('y')}-{date_m.group('m')}-{date_m.group('d')}"
        key = f"episode|{show_norm}|date|{air}"
        label = f"{show_raw or show_norm} — {air}"
        return Identity(
            kind="episode",
            key=key,
            label=label,
            title=label,
            show=show_raw or show_norm,
            air_date=air,
            show_year=show_year,
        )

    season_n = int(s) if s is not None else 0
    episode_n = int(e) if e is not None else 0
    if season_n or episode_n:
        part_m = STORY_PART_RE.search(stem.strip())
        part = part_m.group("part").upper() if part_m else ""
        part_bit = f"|p{part}" if part else ""
        key = f"episode|{show_norm}|{season_n}|{episode_n}{part_bit}"
        ep_label = f"S{season_n:02d}E{episode_n:02d}"
        if part:
            ep_label = f"{ep_label} part {part}"
        label = f"{show_raw or show_norm} — {ep_label}"
        return Identity(
            kind="episode",
            key=key,
            label=label,
            title=label,
            show=show_raw or show_norm,
            season=season_n,
            episode=episode_n,
            show_year=show_year,
        )

    # No episode numbers — do not pretend TV files are the same item
    fallback = normalize_title(strip_quality_tokens(stem)) or normalize_title(stem)
    key = f"episode|{show_norm}|file|{fallback}"
    return Identity(
        kind="episode",
        key=key,
        label=show_raw or stem,
        title=show_raw or stem,
        show=show_raw or show_norm,
    )


def audio_identity(
    file_name: str,
    relative_path: str | None = None,
    display_title: str | None = None,
    album: str | None = None,
) -> Identity:
    stem = Path(file_name).stem
    track = _clean_spaces(strip_quality_tokens(stem))
    track = re.sub(r"^\d{1,3}(?:\s*[-._)\]]\s*|\s+)", "", track).strip() or track
    folders = _folder_title_candidates(relative_path)
    album_name = album or (folders[-1] if folders else "")
    if not album_name and display_title and "—" in display_title:
        album_name = display_title.split("—", 1)[0].strip()
    a = normalize_title(album_name) if album_name else ""
    t = normalize_title(track)
    if a and t:
        key = f"audio|{a}|{t}"
        label = f"{album_name} — {track}"
    else:
        key = f"audio|{t or normalize_title(stem)}"
        label = track or stem
    return Identity(kind="audio", key=key, label=label, title=track, show=album_name or None)


def infer_kind(
    file_name: str,
    relative_path: str | None = None,
    kind: str | None = None,
    extension: str | None = None,
) -> str:
    if kind in {"movie", "episode", "audio", "other"}:
        hinted = kind
    else:
        hinted = None
    ext = (extension or Path(file_name).suffix or "").lower()
    from mmc.config import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS

    if ext in AUDIO_EXTENSIONS:
        return "audio"
    parts = [p.lower() for p in split_path_parts(relative_path)]
    if any(p in TV_LIBRARY_FOLDERS for p in parts[:-1]):
        return "episode"
    if EPISODE_RE.search(file_name) or EPISODE_RE.search(relative_path or ""):
        return "episode"
    if DATE_RE.search(file_name) and any(p in TV_LIBRARY_FOLDERS for p in parts):
        return "episode"
    if hinted == "episode":
        return "episode"
    if hinted == "movie":
        return "movie"
    if ext in VIDEO_EXTENSIONS:
        return "movie"
    return hinted or "other"


def identify(item: dict[str, Any]) -> Identity:
    """Build an Identity from a catalog/scan item dict."""
    file_name = item.get("file_name") or Path(str(item.get("file_path") or "")).name
    rel = item.get("relative_path") or ""
    kind = infer_kind(
        file_name,
        rel,
        kind=item.get("kind"),
        extension=item.get("extension"),
    )
    if kind == "audio":
        ident = audio_identity(
            file_name,
            rel,
            display_title=item.get("display_title"),
            album=item.get("show_name"),
        )
    elif kind == "episode":
        ident = episode_identity(
            file_name,
            rel,
            show_name=item.get("show_name"),
            season=item.get("season"),
            episode=item.get("episode"),
        )
    else:
        ident = movie_identity(
            file_name,
            rel,
            display_title=item.get("display_title"),
        )
    return ident


def alias_keys(ident: Identity) -> set[str]:
    """Extra keys used to merge 'Dune 2021' with 'Dune Part One 2021'."""
    keys = {ident.key}
    if ident.kind != "movie" or not ident.year:
        return keys
    title = normalize_title(ident.title)
    year = ident.year
    disc = f"|cd{ident.disc}" if ident.disc else ""
    m = re.match(r"^(.*) part 1$", title)
    if m and m.group(1).strip():
        keys.add(f"movie|{m.group(1).strip()}|{year}{disc}")
    else:
        keys.add(f"movie|{title} part 1|{year}{disc}")
    return keys
