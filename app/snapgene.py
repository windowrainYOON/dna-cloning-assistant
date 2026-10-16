"""Reader/writer for SnapGene .dna files.

A .dna file is a flat list of blocks:

    1 byte  block type
    4 bytes big-endian payload length
    N bytes payload

Only the blocks this tool understands are decoded (sequence, features,
primers, notes); every other block is kept byte-for-byte so a file that is
read and written back stays loadable in SnapGene.
"""

from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html import unescape
from typing import Any

BLOCK_SEQUENCE = 0
BLOCK_PRIMERS = 5
BLOCK_NOTES = 6
BLOCK_FEATURES = 10
BLOCK_HEADER = 9

# Order SnapGene itself writes blocks in; unknown blocks keep their original
# relative position by sorting on their first-seen index.
_WRITE_ORDER = [9, 0, 3, 17, 8, 10, 5, 6, 13, 35, 20, 14, 28]

COMPLEMENT = str.maketrans("ACGTRYKMSWBDHVNacgtrykmswbdhvn",
                           "TGCAYRMKSWVHDBNtgcayrmkswvhdbn")


def reverse_complement(seq: str) -> str:
    return seq.translate(COMPLEMENT)[::-1]


_TAG_RE = re.compile(r"<[^>]+>")


def _plain(text: str | None) -> str:
    """SnapGene wraps free text in HTML (with unclosed <br>); strip the tags."""
    if not text:
        return ""
    return unescape(_TAG_RE.sub("", text)).replace("\xa0", " ").strip()


@dataclass
class Segment:
    start: int          # 1-based inclusive
    end: int            # 1-based inclusive
    color: str = "#cccccc"
    translated: bool = False


@dataclass
class Feature:
    name: str
    type: str = "misc_feature"
    directionality: int = 1      # 1 = forward, 2 = reverse, 0 = none
    segments: list[Segment] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)
    translation: str = ""

    @property
    def start(self) -> int:
        return min(s.start for s in self.segments)

    @property
    def end(self) -> int:
        return max(s.end for s in self.segments)

    @property
    def color(self) -> str:
        return self.segments[0].color if self.segments else "#cccccc"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "directionality": self.directionality,
            "start": self.start,
            "end": self.end,
            "color": self.color,
            "translation": self.translation,
            "notes": self.notes,
            "segments": [{"start": s.start, "end": s.end, "color": s.color,
                          "translated": s.translated} for s in self.segments],
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Feature":
        segs = d.get("segments") or [{"start": d["start"], "end": d["end"],
                                      "color": d.get("color", "#cccccc")}]
        return Feature(
            name=d.get("name", "unnamed"),
            type=d.get("type", "misc_feature"),
            directionality=int(d.get("directionality", 1)),
            segments=[Segment(int(s["start"]), int(s["end"]),
                              s.get("color", d.get("color", "#cccccc")),
                              bool(s.get("translated", False))) for s in segs],
            notes=d.get("notes", {}) or {},
            translation=d.get("translation", "") or "",
        )


@dataclass
class Primer:
    name: str
    sequence: str
    description: str = ""
    binding_sites: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "sequence": self.sequence,
                "description": self.description, "binding_sites": self.binding_sites}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Primer":
        return Primer(d.get("name", "unnamed"), d.get("sequence", "").strip(),
                      d.get("description", ""), d.get("binding_sites", []) or [])


class SnapGeneFile:
    """A parsed .dna file. Unknown blocks are kept so writing round-trips."""

    def __init__(self) -> None:
        self.sequence: str = ""
        self.is_circular: bool = False
        self._seq_flags: int = 0
        self.features: list[Feature] = []
        self.primers: list[Primer] = []
        self.notes: dict[str, str] = {}
        self._notes_raw: bytes | None = None
        self._raw_blocks: list[tuple[int, bytes]] = []

    # ---------------------------------------------------------------- read

    @classmethod
    def read(cls, path_or_bytes: str | bytes) -> "SnapGeneFile":
        if isinstance(path_or_bytes, str):
            with open(path_or_bytes, "rb") as fh:
                data = fh.read()
        else:
            data = path_or_bytes
        self = cls()
        i = 0
        while i + 5 <= len(data):
            btype = data[i]
            (length,) = struct.unpack(">I", data[i + 1:i + 5])
            body = data[i + 5:i + 5 + length]
            i += 5 + length
            if btype == BLOCK_SEQUENCE:
                self._seq_flags = body[0]
                self.is_circular = bool(body[0] & 0x01)
                self.sequence = body[1:].decode("ascii").upper()
            elif btype == BLOCK_FEATURES:
                self.features = _parse_features(body.decode("utf-8"))
            elif btype == BLOCK_PRIMERS:
                self.primers = _parse_primers(body.decode("utf-8"))
            elif btype == BLOCK_NOTES:
                self._notes_raw = body
                self.notes = _parse_notes(body.decode("utf-8"))
            else:
                self._raw_blocks.append((btype, body))
        if not self.sequence:
            raise ValueError("No DNA sequence block (type 0) found — not a SnapGene .dna file?")
        return self

    # --------------------------------------------------------------- write

    def write(self, path: str) -> None:
        with open(path, "wb") as fh:
            fh.write(self.to_bytes())

    def to_bytes(self) -> bytes:
        blocks: list[tuple[int, bytes]] = list(self._raw_blocks)
        flags = (self._seq_flags | 0x01) if self.is_circular else (self._seq_flags & ~0x01)
        blocks.append((BLOCK_SEQUENCE, bytes([flags]) + self.sequence.encode("ascii")))
        blocks.append((BLOCK_FEATURES, _write_features(self.features).encode("utf-8")))
        blocks.append((BLOCK_PRIMERS, _write_primers(self.primers).encode("utf-8")))
        if self._notes_raw is not None:
            # Notes carry timestamps and attributes this tool does not model,
            # so the original block is written back unchanged.
            blocks.append((BLOCK_NOTES, self._notes_raw))
        elif self.notes:
            blocks.append((BLOCK_NOTES, _write_notes(self.notes).encode("utf-8")))

        def key(item: tuple[int, bytes]) -> int:
            return _WRITE_ORDER.index(item[0]) if item[0] in _WRITE_ORDER else len(_WRITE_ORDER)

        out = bytearray()
        for btype, body in sorted(blocks, key=key):
            out += bytes([btype]) + struct.pack(">I", len(body)) + body
        return bytes(out)

    # ----------------------------------------------------------- utilities

    def subsequence(self, start: int, end: int) -> str:
        """1-based inclusive slice; wraps the origin on a circular sequence."""
        n = len(self.sequence)
        if start <= end:
            return self.sequence[start - 1:end]
        if not self.is_circular:
            raise ValueError("start > end is only meaningful on a circular sequence")
        return self.sequence[start - 1:] + self.sequence[:end]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "length": len(self.sequence),
            "is_circular": self.is_circular,
            "features": [f.to_dict() for f in self.features],
            "primers": [p.to_dict() for p in self.primers],
            "notes": self.notes,
        }

    def apply_edit(self, start: int, end: int, replacement: str) -> None:
        """Replace sequence[start..end] (1-based inclusive) and shift features.

        A feature that the edit overlaps is trimmed to the untouched part; one
        that the edit swallows whole is dropped.
        """
        replacement = "".join(replacement.split()).upper()
        removed = end - start + 1
        delta = len(replacement) - removed
        self.sequence = self.sequence[:start - 1] + replacement + self.sequence[end:]
        kept: list[Feature] = []
        for feat in self.features:
            segs: list[Segment] = []
            for seg in feat.segments:
                s, e = _shift_range(seg.start, seg.end, start, end, delta)
                if s is not None:
                    segs.append(Segment(s, e, seg.color, seg.translated))
            if segs:
                feat.segments = segs
                kept.append(feat)
        self.features = kept


def _shift_range(s: int, e: int, start: int, end: int, delta: int):
    """Map a 1-based feature range across an edit of [start, end]."""
    if e < start:                       # entirely before the edit
        return s, e
    if s > end:                         # entirely after it
        return s + delta, e + delta
    if s >= start and e <= end:         # swallowed
        return None, None
    if s < start and e > end:           # spans the edit
        return s, e + delta
    if s < start:                       # overlaps the left edge
        return s, start - 1
    return end + 1 + delta, e + delta   # overlaps the right edge


# ------------------------------------------------------------- XML parsing

def _parse_features(xml: str) -> list[Feature]:
    root = ET.fromstring(xml)
    out: list[Feature] = []
    for el in root.findall("Feature"):
        segments = []
        for seg in el.findall("Segment"):
            rng = seg.get("range", "")
            if "-" not in rng:
                continue
            a, b = rng.split("-", 1)
            segments.append(Segment(int(a), int(b), seg.get("color", "#cccccc"),
                                    seg.get("translated") == "1"))
        if not segments:
            continue
        notes, translation = {}, ""
        for q in el.findall("Q"):
            name = q.get("name", "")
            v = q.find("V")
            if v is None:
                continue
            value = v.get("text") or v.get("int") or v.get("predef") or ""
            if name == "translation":
                translation = value
            else:
                notes[name] = _plain(value)
        out.append(Feature(name=el.get("name", "unnamed"), type=el.get("type", "misc_feature"),
                           directionality=int(el.get("directionality", "0") or 0),
                           segments=segments, notes=notes, translation=translation))
    return out


def _parse_primers(xml: str) -> list[Primer]:
    root = ET.fromstring(xml)
    out: list[Primer] = []
    for el in root.findall("Primer"):
        sites = []
        for site in el.findall("BindingSite"):
            if site.get("simplified") == "1":
                continue
            rng = site.get("location", "")
            a, b = (rng.split("-", 1) + [""])[:2] if "-" in rng else ("", "")
            sites.append({
                "start": int(a) if a else None,
                "end": int(b) if b else None,
                "strand": int(site.get("boundStrand", "0")),
                "annealed_bases": site.get("annealedBases", ""),
                "tm_snapgene": float(site.get("meltingTemperature", "0") or 0),
            })
        out.append(Primer(el.get("name", "unnamed"), el.get("sequence", ""),
                          _plain(el.get("description")), sites))
    return out


def _parse_notes(xml: str) -> dict[str, str]:
    root = ET.fromstring(xml)
    return {child.tag: (child.text or "").strip() for child in root}


# ------------------------------------------------------------- XML writing

def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _write_features(features: list[Feature]) -> str:
    parts = ['<?xml version="1.0"?>', f'<Features nextValidID="{len(features)}">']
    for idx, feat in enumerate(features):
        attrs = (f'recentID="{idx}" name="{_esc(feat.name)}" type="{_esc(feat.type)}"'
                 f' allowSegmentOverlaps="0" consecutiveTranslationNumbering="1"')
        if feat.directionality:
            attrs += f' directionality="{feat.directionality}"'
        parts.append(f"<Feature {attrs}>")
        for seg in feat.segments:
            translated = ' translated="1"' if seg.translated else ""
            parts.append(f'<Segment range="{seg.start}-{seg.end}" color="{_esc(seg.color)}"'
                         f' type="standard"{translated}/>')
        for key, value in feat.notes.items():
            parts.append(f'<Q name="{_esc(key)}"><V text="{_esc(value)}"/></Q>')
        if feat.translation:
            parts.append(f'<Q name="translation"><V text="{_esc(feat.translation)}"/></Q>')
        parts.append("</Feature>")
    parts.append("</Features>")
    return "".join(parts)


def _write_primers(primers: list[Primer]) -> str:
    parts = ['<?xml version="1.0"?>', f'<Primers nextValidID="{len(primers)}">']
    for idx, primer in enumerate(primers):
        parts.append(f'<Primer recentID="{idx}" name="{_esc(primer.name)}"'
                     f' sequence="{_esc(primer.sequence)}"'
                     f' description="{_esc(primer.description)}"/>')
    parts.append("</Primers>")
    return "".join(parts)


def _write_notes(notes: dict[str, str]) -> str:
    parts = ["<Notes>"]
    for key, value in notes.items():
        parts.append(f"<{key}>{_esc(value)}</{key}>")
    parts.append("</Notes>")
    return "".join(parts)
