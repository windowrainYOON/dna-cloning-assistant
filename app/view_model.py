"""Presentation logic for the Tk interface, kept free of Tk itself.

Everything here turns parsed plasmid data into the rows, spans, arcs and text
blocks the widgets display, so the layout can be tested without a display.
"""

from __future__ import annotations

import math
from typing import Any

from .snapgene import Feature, reverse_complement

LINE_WIDTH = 60
GROUP = 10


def _hex_to_rgb(color: str) -> tuple[int, int, int] | None:
    text = (color or "").lstrip("#")
    if len(text) != 6:
        return None
    try:
        value = int(text, 16)
    except ValueError:
        return None
    return (value >> 16) & 255, (value >> 8) & 255, value & 255


def display_color(color: str, dark: bool = True) -> str:
    """SnapGene stores some features as white or near-black; keep them visible."""
    rgb = _hex_to_rgb(color)
    if rgb is None:
        return "#9aa3b2"
    lum = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255
    if dark and min(rgb) > 225:      # near white: invisible on a dark map
        return "#9aa3b2"
    if not dark and lum < 0.12:
        return "#555e6e"
    return "#" + "".join(f"{c:02x}" for c in rgb)


def grouped(bases: str, group: int = GROUP) -> str:
    """ACGT… split into blocks of ten, the way sequence editors print it."""
    return " ".join(bases[i:i + group] for i in range(0, len(bases), group))


def column_of(offset: int, gutter: int, group: int = GROUP) -> int:
    """Text column of the base at `offset` within a line, blocks included."""
    return gutter + offset + offset // group


def sequence_rows(sequence: str, features: list[Feature], *, width: int = LINE_WIDTH,
                  show_complement: bool = False,
                  show_tracks: bool = True) -> list[dict[str, Any]]:
    """Lay the sequence out line by line with the feature tracks under it.

    Each row is one line of text plus the spans to colour:
        {"text": str, "kind": "sequence"|"complement"|"track",
         "spans": [(col_start, col_end, color)], "first": int, "last": int}
    """
    rows: list[dict[str, Any]] = []
    gutter = len(f"{len(sequence):,}") + 2
    for start in range(0, len(sequence), width):
        chunk = sequence[start:start + width]
        first, last = start + 1, start + len(chunk)
        number = f"{first:,}".rjust(gutter - 2) + "  "
        rows.append({"kind": "sequence", "text": number + grouped(chunk),
                     "first": first, "last": last, "spans": [], "gutter": gutter})
        if show_complement:
            rows.append({"kind": "complement",
                         "text": " " * gutter + grouped(reverse_complement(chunk)[::-1]),
                         "first": first, "last": last, "spans": [], "gutter": gutter})
        if not show_tracks:
            continue
        for feat in features:
            if feat.end < first or feat.start > last:
                continue
            marks = []
            for offset in range(len(chunk)):
                pos = first + offset
                if pos < feat.start or pos > feat.end:
                    marks.append(" ")
                elif pos == feat.start:
                    marks.append("◀" if feat.directionality == 2 else "├")
                elif pos == feat.end:
                    marks.append("▶" if feat.directionality == 1 else "┤")
                else:
                    marks.append("─")
            bar = grouped("".join(marks))
            label = feat.name + (f" ({feat.type})" if feat.type != "misc_feature" else "")
            text = " " * gutter + bar + "  " + label
            rows.append({"kind": "track", "text": text, "first": first, "last": last,
                         "gutter": gutter, "feature": feat.name,
                         "spans": [(gutter, len(text), display_color(feat.color))]})
    return rows


def map_arcs(features: list[Feature], length: int) -> list[dict[str, Any]]:
    """Lay features onto rings of a circular map, nothing overlapping in a ring.

    Angles follow Tk's convention: degrees counter-clockwise from 3 o'clock,
    with position 1 at the top, so a feature runs clockwise as a negative
    extent.
    """
    rings: list[list[Feature]] = []
    arcs: list[dict[str, Any]] = []
    for feat in sorted(features, key=lambda f: (f.start - f.end, f.start)):
        ring = None
        for index, members in enumerate(rings):
            if not any(feat.start <= other.end and other.start <= feat.end
                       for other in members):
                members.append(feat)
                ring = index
                break
        if ring is None:
            rings.append([feat])
            ring = len(rings) - 1
        span = feat.end - feat.start + 1
        arcs.append({
            "name": feat.name,
            "type": feat.type,
            "ring": ring,
            "start_angle": 90.0 - 360.0 * (feat.start - 1) / length,
            "extent": -360.0 * span / length,
            "mid_angle": 90.0 - 360.0 * ((feat.start - 1 + feat.end) / 2) / length,
            "color": display_color(feat.color),
            "directionality": feat.directionality,
            "label": feat.name if span > length / 60 else "",
            "start": feat.start,
            "end": feat.end,
        })
    return arcs


def polar(cx: float, cy: float, radius: float, angle_deg: float) -> tuple[float, float]:
    """Canvas point at `angle_deg` (Tk convention) on a circle."""
    a = math.radians(angle_deg)
    return cx + radius * math.cos(a), cy - radius * math.sin(a)


def feature_detail(feat: Feature) -> str:
    """Everything SnapGene stored on a feature, as a block of text."""
    strand = {1: "forward (top strand)", 2: "reverse (bottom strand)"}.get(
        feat.directionality, "방향 없음")
    lines = [
        f"{feat.name}",
        f"{'위치':<10} {feat.start:,}–{feat.end:,} "
        f"({feat.end - feat.start + 1:,} bp, {strand})",
        f"{'종류':<10} {feat.type}",
        f"{'색':<10} {feat.color}",
    ]
    if len(feat.segments) > 1:
        lines.append(f"{'조각':<10} " + ", ".join(f"{s.start:,}–{s.end:,}" for s in feat.segments))
    for key, value in (feat.notes or {}).items():
        if value:
            lines.append(f"{key:<10} {value}")
    if feat.translation:
        protein = feat.translation.rstrip("*")
        lines.append(f"{'번역':<10} {len(protein)} aa")
        lines.append("")
        for i in range(0, len(feat.translation), 60):
            lines.append("  " + feat.translation[i:i + 60])
    return "\n".join(lines)


def _time(seconds: int | None) -> str:
    if seconds is None:
        return "∞"
    if seconds >= 60:
        rest = seconds % 60
        return f"{seconds // 60}분" + (f" {rest}초" if rest else "")
    return f"{seconds}초"


def pcr_report(result: dict[str, Any]) -> str:
    """The PCR result as the text shown in the Pfu-X tab."""
    out: list[str] = []
    for primer in result.get("primers", []):
        out.append(f"■ {primer['name']}")
        out.append(f"   5'-{primer['sequence']}-3'")
        out.append(f"   길이 {primer['length']} nt · GC {primer['gc']}% · "
                   f"Tm(annealing 부분) {primer['tm_anneal']} °C · "
                   f"Tm(전체) {primer['tm_full']} °C")
        if primer.get("tail"):
            out.append(f"   5' tail {len(primer['tail'])} nt · {primer['tail']}")
        binding = primer.get("binding")
        if binding:
            strand = "top strand →" if binding["strand"] == 0 else "bottom strand ←"
            out.append(f"   결합 {binding['start']:,}–{binding['end']:,} ({strand}), "
                       f"{binding['matched_len']} nt 완전일치"
                       + (f", tail 불일치 {binding['tail_mismatches']} nt"
                          if binding.get("tail_mismatches") else ""))
        else:
            out.append("   결합 위치를 찾지 못했습니다.")
        for warning in primer.get("warnings", []):
            out.append(f"   ! {warning}")
        out.append("")

    if not result.get("program"):
        out.extend(result.get("notes") or ["PCR 조건을 계산할 수 없습니다."])
        return "\n".join(out + ["", _assumptions(result)])

    mode = ("whole-plasmid site-directed mutagenesis (inverse PCR)"
            if result["mode"] == "whole_plasmid" else "일반 증폭 (amplicon)")
    product = f"{result['product_length']:,} bp" if result.get("product_length") else "계산 불가"
    out += [
        "─" * 64,
        f"모드        {mode}",
        f"예상 산물   {product}",
        f"Annealing   {result['annealing_temp']} °C",
        "",
        "싸이클링 프로그램",
    ]
    for step in result["program"]:
        repeat = f"{step['cycles']} 사이클" if step["cycles"] > 1 else "1회"
        out.append(f"   {step['name']:<22} {step['temp']:>5} °C   "
                   f"{_time(step['time_s']):>8}   {repeat}")
    if result.get("two_stage"):
        stage1, stage2 = result["two_stage"]["stage1"], result["two_stage"]["stage2"]
        out += ["", f"   2단계: {stage1['cycles']} 사이클 @ {stage1['annealing_temp']} °C → "
                    f"{stage2['cycles']} 사이클 @ {stage2['annealing_temp']} °C",
                f"   {stage1['reason']}"]
    for note in result.get("notes") or []:
        out += ["", f"   · {note}"]

    mix = result["mix"]
    out += ["", f"반응 믹스 ({mix['total_uL']:.0f} µL)"]
    for row in mix["rows"]:
        volume = (f"{row['volume_uL']} µL" if isinstance(row["volume_uL"], (int, float))
                  else str(row["volume_uL"]))
        out.append(f"   {row['component']:<34} {volume:>12}   {row['final']}")
    out += ["", f"   {mix['note']}", "", _assumptions(result)]
    return "\n".join(out)


def _assumptions(result: dict[str, Any]) -> str:
    labels = {"tm": "Tm 계산", "annealing": "Annealing 온도", "extension": "신장 시간",
              "cycles": "사이클 수", "caveat": "주의"}
    lines = ["계산 근거와 가정"]
    for key, value in (result.get("assumptions") or {}).items():
        lines.append(f"   {labels.get(key, key)}: {value}")
    return "\n".join(lines)
