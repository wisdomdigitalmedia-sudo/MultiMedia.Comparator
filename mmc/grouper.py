"""Cluster media items that represent the same title / episode / track."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from mmc.identity import Identity, alias_keys, identify
from mmc.quality import QualityScore, pick_winner, score_item
from mmc.filename_meta import parse_filename_meta
from mmc.probe import ProbeResult


@dataclass
class ScoredCopy:
    item: dict[str, Any]
    identity: Identity
    score: QualityScore
    rank: int = 0
    is_winner: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "item": self.item,
            "identity": self.identity.as_dict(),
            "score": self.score.as_dict(),
            "rank": self.rank,
            "is_winner": self.is_winner,
        }


@dataclass
class DuplicateGroup:
    key: str
    kind: str
    label: str
    copies: list[ScoredCopy] = field(default_factory=list)
    editions: list[str] = field(default_factory=list)
    mixed_editions: bool = False
    score_gap: float = 0.0

    @property
    def winner(self) -> ScoredCopy | None:
        for c in self.copies:
            if c.is_winner:
                return c
        return self.copies[0] if self.copies else None

    @property
    def extras(self) -> list[ScoredCopy]:
        return [c for c in self.copies if not c.is_winner]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "label": self.label,
            "copy_count": len(self.copies),
            "editions": self.editions,
            "mixed_editions": self.mixed_editions,
            "score_gap": self.score_gap,
            "copies": [c.as_dict() for c in self.copies],
            "winner_path": (self.winner.item.get("file_path") if self.winner else None),
        }


def _union_find_merge(items: list[tuple[int, Identity]]) -> dict[int, int]:
    """Merge movie identities that share an alias (Dune / Dune Part One)."""
    parent = {i: i for i, _ in items}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    buckets: dict[str, list[int]] = defaultdict(list)
    for idx, ident in items:
        for key in alias_keys(ident):
            buckets[key].append(idx)
    for ids in buckets.values():
        first = ids[0]
        for other in ids[1:]:
            union(first, other)
    return {i: find(i) for i, _ in items}


def _is_sample_item(item: dict[str, Any]) -> bool:
    name = (item.get("file_name") or "").lower()
    return (
        name.startswith("sample-")
        or name.startswith("sample.")
        or ".sample." in name
        or "-sample." in name
    )


def _split_conflicting_show_years(
    members: list[tuple[dict[str, Any], Any]],
) -> list[list[tuple[dict[str, Any], Any]]]:
    """In The Dark 2017 vs 2019 share a name — split when both years appear."""
    years = {ident.show_year for _it, ident in members if ident.show_year}
    if len(years) <= 1:
        return [members]
    buckets: dict[int, list] = {}
    unknown: list = []
    for pair in members:
        y = pair[1].show_year
        if y:
            buckets.setdefault(y, []).append(pair)
        else:
            unknown.append(pair)
    # Attach unknown-year rips to the largest year bucket
    if unknown and buckets:
        biggest = max(buckets, key=lambda k: len(buckets[k]))
        buckets[biggest].extend(unknown)
    elif unknown:
        return [unknown]
    return list(buckets.values())


def group_items(
    items: list[dict[str, Any]],
    probes: dict[str, ProbeResult] | None = None,
    min_copies: int = 2,
) -> list[DuplicateGroup]:
    """
    Identify, cluster, score, and pick a winner for each duplicate set.

    `probes` is keyed by file_path (or any item['id'] string if present).
    """
    probes = probes or {}
    identified: list[tuple[dict[str, Any], Identity]] = []
    for item in items:
        if _is_sample_item(item):
            continue
        ident = identify(item)
        item = dict(item)
        item["identity_key"] = ident.key
        item["identity_label"] = ident.label
        item["edition"] = ident.edition
        item["is_3d"] = ident.is_3d
        item["kind"] = ident.kind
        identified.append((item, ident))

    # Primary bucket by exact key
    exact: dict[str, list[tuple[int, dict[str, Any], Identity]]] = defaultdict(list)
    for i, (item, ident) in enumerate(identified):
        exact[ident.key].append((i, item, ident))

    # Merge movie aliases across keys
    movie_pairs = [(i, ident) for i, (_it, ident) in enumerate(identified) if ident.kind == "movie"]
    roots = _union_find_merge(movie_pairs) if movie_pairs else {}

    merged: dict[str, list[tuple[dict[str, Any], Identity]]] = defaultdict(list)
    used: set[int] = set()
    for i, (item, ident) in enumerate(identified):
        if ident.kind == "movie" and i in roots:
            merged[f"movie-root:{roots[i]}"].append((item, ident))
            used.add(i)
    for i, (item, ident) in enumerate(identified):
        if i in used:
            continue
        merged[ident.key].append((item, ident))

    groups: list[DuplicateGroup] = []
    for members in merged.values():
        clusters = (
            _split_conflicting_show_years(members)
            if members and members[0][1].kind == "episode"
            else [members]
        )
        for cluster in clusters:
            _emit_group(cluster, min_copies, probes, groups)
    groups.sort(key=lambda g: (-len(g.copies), -g.score_gap, g.label.lower()))
    return groups


def _emit_group(
    members: list[tuple[dict[str, Any], Identity]],
    min_copies: int,
    probes: dict[str, ProbeResult],
    groups: list[DuplicateGroup],
) -> None:
    if len(members) < min_copies:
        return
    members_sorted_keys = sorted(members, key=lambda m: len(m[1].key))
    canon = members_sorted_keys[0][1]
    scored_copies: list[ScoredCopy] = []
    for item, ident in members:
        path = str(item.get("file_path") or "")
        probe = probes.get(path)
        if probe is None and item.get("id") is not None:
            probe = probes.get(str(item["id"]))
        meta = parse_filename_meta(item.get("file_name") or "", item.get("relative_path"))
        score = score_item(item, probe=probe, filename_meta=meta)
        scored_copies.append(ScoredCopy(item=item, identity=ident, score=score))

    pairs = [(c.item, c.score) for c in scored_copies]
    win_i = pick_winner(pairs)
    ordered = sorted(
        range(len(scored_copies)),
        key=lambda i: (
            scored_copies[i].score.total,
            int(scored_copies[i].item.get("size_bytes") or 0),
        ),
        reverse=True,
    )
    for rank, idx in enumerate(ordered, start=1):
        scored_copies[idx].rank = rank
        scored_copies[idx].is_winner = idx == win_i
    scored_copies.sort(key=lambda c: c.rank)

    editions = sorted({c.identity.edition for c in scored_copies if c.identity.edition})
    totals = [c.score.total for c in scored_copies]
    gap = round(max(totals) - min(totals), 2) if totals else 0.0
    titles = {normalize_keep(c.identity) for c in scored_copies}
    label = next(iter(titles)) if len(titles) == 1 else min(titles, key=len)

    key = canon.key
    years = {c.identity.show_year for c in scored_copies if c.identity.show_year}
    if canon.kind == "episode" and len(years) == 1:
        y = next(iter(years))
        key = f"{key}|y{y}"
        if str(y) not in label:
            label = f"{label} ({y})"

    groups.append(
        DuplicateGroup(
            key=key,
            kind=canon.kind,
            label=label,
            copies=scored_copies,
            editions=editions,
            mixed_editions=len(editions) > 1,
            score_gap=gap,
        )
    )


def normalize_keep(ident: Identity) -> str:
    year = f" ({ident.year})" if ident.year else ""
    if ident.kind == "episode":
        return ident.label
    return f"{ident.title}{year}"


def groups_to_jsonable(groups: list[DuplicateGroup]) -> list[dict[str, Any]]:
    return [g.as_dict() for g in groups]
