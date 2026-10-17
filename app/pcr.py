"""Primer analysis and Pfu-X PCR condition calculation.

Tm model
--------
Nearest-neighbour thermodynamics, SantaLucia (1998) unified parameters
(PNAS 95:1460), with the initiation terms of SantaLucia & Hicks (2004):

    Tm = (1000 * dH) / (dS + R * ln(CT / 4)) - 273.15

CT is total primer strand concentration and the /4 factor applies to
non-self-complementary duplexes. Salt is corrected on the entropy term with
the Owczarzy/SantaLucia monovalent relation

    dS_salt = dS + 0.368 * (N - 1) * ln([Na+ equivalent])

and Mg2+ is folded in as a monovalent equivalent, [Na+]eq = [Na+] +
120 * sqrt([Mg2+] - [dNTP]) (Ahsen et al. 2001). Defaults match a typical
Pfu-X reaction: 2 mM Mg2+, 0.2 mM dNTP, 10 mM monovalent from the buffer,
0.25 uM each primer.

Cycling model
-------------
Pfu-X is a proofreading Pfu variant supplied as a 2x premix by Solgent. The
defaults below follow the vendor's generic protocol and are *starting points*
that the UI lets you override:

  * initial denaturation  95 C, 2 min
  * denaturation          95 C, 20 s
  * annealing             Ta = min(Tm_fwd, Tm_rev) - 5 C, clamped to 50-68 C, 30 s
  * extension             72 C, 30 s per kb of product (min 30 s)
  * cycles                30 for a cloning PCR, 18 for whole-plasmid SDM
  * final extension       72 C, 5 min

Primers with a 5' tail (restriction site, tag, mutagenic mismatch) anneal
only through their 3' portion in the first cycles, so the annealing Tm is
computed from the template-matching part and a two-stage cycling program is
suggested: 5 cycles at the annealing-portion Ta, then the rest at the Ta of
the full-length primer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .snapgene import reverse_complement

R = 1.987  # cal/(K*mol)

# SantaLucia 1998 unified NN parameters: dH (kcal/mol), dS (cal/(K*mol))
NN = {
    "AA": (-7.9, -22.2), "TT": (-7.9, -22.2),
    "AT": (-7.2, -20.4), "TA": (-7.2, -21.3),
    "CA": (-8.5, -22.7), "TG": (-8.5, -22.7),
    "GT": (-8.4, -22.4), "AC": (-8.4, -22.4),
    "CT": (-7.8, -21.0), "AG": (-7.8, -21.0),
    "GA": (-8.2, -22.2), "TC": (-8.2, -22.2),
    "CG": (-10.6, -27.2), "GC": (-9.8, -24.4),
    "GG": (-8.0, -19.9), "CC": (-8.0, -19.9),
}
INIT_GC = (0.1, -2.8)   # initiation with terminal G or C
INIT_AT = (2.3, 4.1)    # initiation with terminal A or T


@dataclass
class Conditions:
    """Reaction and cycling knobs the caller may override."""
    primer_conc_nM: float = 250.0
    na_mM: float = 10.0
    mg_mM: float = 2.0
    dntp_mM: float = 0.2
    ta_offset: float = 5.0          # Ta = min(Tm) - offset
    ta_min: float = 50.0
    ta_max: float = 68.0
    extension_s_per_kb: float = 30.0
    min_extension_s: float = 30.0
    cycles: int = 30
    sdm_cycles: int = 18
    reaction_uL: float = 50.0

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> "Conditions":
        c = Conditions()
        for key, value in (d or {}).items():
            if hasattr(c, key) and value not in (None, ""):
                setattr(c, key, type(getattr(c, key))(value))
        return c


def clean(seq: str) -> str:
    return "".join(ch for ch in seq.upper() if ch in "ACGTRYKMSWBDHVN")


def gc_percent(seq: str) -> float:
    seq = clean(seq)
    if not seq:
        return 0.0
    return 100.0 * sum(ch in "GC" for ch in seq) / len(seq)


def na_equivalent(c: Conditions) -> float:
    """Monovalent-equivalent cation concentration in mol/L."""
    free_mg = max(c.mg_mM - c.dntp_mM, 0.0)
    return (c.na_mM + 120.0 * math.sqrt(free_mg)) / 1000.0


def tm_nearest_neighbour(seq: str, c: Conditions | None = None) -> float:
    """Tm in C for a primer annealing to its perfect complement."""
    c = c or Conditions()
    seq = clean(seq)
    if len(seq) < 2 or any(ch not in "ACGT" for ch in seq):
        return float("nan")
    dh, ds = 0.0, 0.0
    for i in range(len(seq) - 1):
        pair = seq[i:i + 2]
        if pair not in NN:
            return float("nan")
        d_h, d_s = NN[pair]
        dh += d_h
        ds += d_s
    for end in (seq[0], seq[-1]):
        d_h, d_s = INIT_GC if end in "GC" else INIT_AT
        dh += d_h
        ds += d_s
    ds += 0.368 * (len(seq) - 1) * math.log(na_equivalent(c))
    ct = c.primer_conc_nM * 1e-9
    return (1000.0 * dh) / (ds + R * math.log(ct / 4.0)) - 273.15


def tm_wallace(seq: str) -> float:
    """2(A+T) + 4(G+C); only meaningful for short, simple oligos."""
    seq = clean(seq)
    at = sum(ch in "AT" for ch in seq)
    gc = sum(ch in "GC" for ch in seq)
    return 2 * at + 4 * gc


def self_complementarity(seq: str) -> dict[str, int]:
    """Crude hairpin / self-dimer / 3'-dimer scores (longest match length)."""
    seq = clean(seq)
    rc = reverse_complement(seq)
    best_dimer = 0
    for size in range(4, min(len(seq), 12) + 1):
        if any(seq[i:i + size] in rc for i in range(len(seq) - size + 1)):
            best_dimer = size
    three_prime = 0
    for size in range(3, min(len(seq), 8) + 1):
        if seq[-size:] in rc:
            three_prime = size
    hairpin = 0
    for size in range(4, min(len(seq) // 2, 10) + 1):
        for i in range(len(seq) - size):
            stem = seq[i:i + size]
            if reverse_complement(stem) in seq[i + size + 3:]:
                hairpin = max(hairpin, size)
    return {"self_dimer": best_dimer, "three_prime_dimer": three_prime, "hairpin": hairpin}


# ------------------------------------------------------- template matching

@dataclass
class Binding:
    strand: int            # 0 = top (forward primer), 1 = bottom (reverse primer)
    start: int             # 1-based inclusive, on the top strand
    end: int
    matched_len: int       # length of the perfect 3'-anchored match
    tail_mismatches: int   # bases of the tail that differ from the adjacent template
    tail: str              # 5' portion beyond the perfect match

    @property
    def three_prime_pos(self) -> int:
        """Top-strand coordinate of the primer's 3' base."""
        return self.end if self.strand == 0 else self.start


def find_binding(primer: str, template: str, circular: bool,
                 min_match: int = 10) -> Binding | None:
    """Locate a primer on a template by its 3'-anchored annealing portion.

    The annealing portion is the longest stretch that matches the template
    perfectly when counted from the primer's 3' end — the part that primes in
    the first cycle. Everything 5' of it (a restriction site, a tag, a
    mutagenic mismatch and whatever lies beyond it) is reported as the tail,
    which is how SnapGene annotates its own binding sites.
    `tail_mismatches` counts how many of those tail bases differ from the
    template they overhang, which separates a mutagenic tail from one that is
    simply added sequence.

    Positions are 1-based on the top strand, the same coordinate system the
    features use (SnapGene's own primer locations are one lower).
    """
    primer = clean(primer)
    template = clean(template)
    if len(primer) < min_match or not template:
        return None
    search = template + (template[:len(primer)] if circular else "")

    best: Binding | None = None
    for strand in (0, 1):
        probe = primer if strand == 0 else reverse_complement(primer)
        anchor = probe[-min_match:] if strand == 0 else probe[:min_match]
        pos = -1
        while True:
            pos = search.find(anchor, pos + 1)
            if pos < 0:
                break
            if strand == 0:
                end = pos + min_match                 # 0-based exclusive
                matched = min_match
                while (matched < len(probe) and end - matched - 1 >= 0
                       and probe[-matched - 1] == search[end - matched - 1]):
                    matched += 1
                start0 = end - matched
                cand = Binding(0, start0 % len(template) + 1,
                               (end - 1) % len(template) + 1, matched, 0,
                               primer[:len(primer) - matched])
                over = [search[start0 - k - 1] for k in range(min(start0, len(cand.tail)))]
                cand.tail_mismatches = sum(1 for k, base in enumerate(over)
                                           if cand.tail[len(cand.tail) - 1 - k] != base)
            else:
                start0 = pos
                matched = min_match
                while (matched < len(probe) and start0 + matched < len(search)
                       and probe[matched] == search[start0 + matched]):
                    matched += 1
                end0 = start0 + matched               # 0-based exclusive
                tail = primer[:len(primer) - matched]
                cand = Binding(1, start0 % len(template) + 1,
                               (end0 - 1) % len(template) + 1, matched, 0, tail)
                rc_tail = reverse_complement(tail)
                over = search[end0:end0 + len(rc_tail)]
                cand.tail_mismatches = sum(1 for a, b in zip(rc_tail, over) if a != b)
            if cand.matched_len >= min_match and (best is None or
                                                  cand.matched_len > best.matched_len):
                best = cand
    return best


def annealing_portion(primer: str, binding: Binding | None) -> str:
    primer = clean(primer)
    if binding is None:
        return primer
    return primer[len(primer) - binding.matched_len:]


# -------------------------------------------------------------- the report

@dataclass
class PrimerReport:
    name: str
    sequence: str
    length: int
    gc: float
    tm_full: float
    tm_anneal: float
    binding: Binding | None
    tail: str
    warnings: list[str] = field(default_factory=list)
    structure: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        b = self.binding
        return {
            "name": self.name, "sequence": self.sequence, "length": self.length,
            "gc": round(self.gc, 1),
            "tm_full": None if math.isnan(self.tm_full) else round(self.tm_full, 1),
            "tm_anneal": None if math.isnan(self.tm_anneal) else round(self.tm_anneal, 1),
            "tail": self.tail,
            "binding": None if b is None else {
                "strand": b.strand, "start": b.start, "end": b.end,
                "matched_len": b.matched_len, "tail_mismatches": b.tail_mismatches,
            },
            "warnings": self.warnings, "structure": self.structure,
        }


def analyse_primer(name: str, sequence: str, template: str | None,
                   circular: bool, c: Conditions) -> PrimerReport:
    seq = clean(sequence)
    binding = find_binding(seq, template, circular) if template else None
    anneal = annealing_portion(seq, binding)
    tm_full = tm_nearest_neighbour(seq, c)
    tm_anneal = tm_nearest_neighbour(anneal, c)
    warnings: list[str] = []
    if len(seq) < 18:
        warnings.append("프라이머가 18 nt보다 짧습니다 — 특이성이 떨어질 수 있습니다.")
    if gc_percent(seq) < 40 or gc_percent(seq) > 65:
        warnings.append("GC 함량이 40-65% 범위를 벗어납니다.")
    if seq[-1:] not in ("G", "C"):
        warnings.append("3' 말단이 G/C가 아닙니다 (GC clamp 없음).")
    if "GGGG" in seq or "CCCC" in seq or "AAAAA" in seq or "TTTTT" in seq:
        warnings.append("동일 염기 반복이 4-5개 이상 있습니다.")
    if binding is None and template:
        warnings.append("주형에서 결합 위치를 찾지 못했습니다 (3' 말단 8 nt 완전일치 기준).")
    structure = self_complementarity(seq)
    if structure["three_prime_dimer"] >= 4:
        warnings.append("3' 말단 self-dimer 가능성이 있습니다.")
    if structure["hairpin"] >= 6:
        warnings.append("hairpin 형성 가능성이 있습니다.")
    return PrimerReport(name or "primer", seq, len(seq), gc_percent(seq),
                        tm_full, tm_anneal, binding, binding.tail if binding else "",
                        warnings, structure)


def _product(fwd: Binding, rev: Binding, template_len: int, circular: bool,
             fwd_tail: int, rev_tail: int) -> tuple[int, str, bool]:
    """Return (product length incl. tails, mode, ok)."""
    start = fwd.start
    end = rev.end
    if start <= end:
        core = end - start + 1
        outward = False
    else:
        if not circular:
            return 0, "invalid", False
        core = template_len - start + 1 + end
        outward = True
    mode = "whole_plasmid" if (outward and core > 0.6 * template_len) else "amplicon"
    return core + fwd_tail + rev_tail, mode, True


def design_pcr(primers: list[dict[str, Any]], template: str | None, circular: bool,
               conditions: dict[str, Any] | None = None) -> dict[str, Any]:
    """Analyse one or two primers and emit a Pfu-X cycling program."""
    c = Conditions.from_dict(conditions)
    reports = [analyse_primer(p.get("name", f"primer {i + 1}"), p.get("sequence", ""),
                              template, circular, c)
               for i, p in enumerate(primers) if clean(p.get("sequence", ""))]
    result: dict[str, Any] = {
        "primers": [r.to_dict() for r in reports],
        "conditions": c.__dict__,
        "assumptions": ASSUMPTIONS,
    }
    if len(reports) < 2:
        result["program"] = None
        result["notes"] = ["PCR 조건을 계산하려면 forward/reverse 프라이머 2개가 필요합니다."]
        return result

    fwd_r, rev_r = reports[0], reports[1]
    notes: list[str] = []
    if fwd_r.binding and rev_r.binding and fwd_r.binding.strand == rev_r.binding.strand:
        notes.append("두 프라이머가 같은 가닥에 결합합니다 — 방향을 확인하세요.")
        fwd_b = rev_b = None
    else:
        fwd_b = fwd_r.binding if (fwd_r.binding and fwd_r.binding.strand == 0) else rev_r.binding
        rev_b = rev_r.binding if (rev_r.binding and rev_r.binding.strand == 1) else fwd_r.binding
        if fwd_b is rev_b:
            fwd_b = rev_b = None

    product_len, mode = None, "unknown"
    if fwd_b is not None and rev_b is not None and template:
        fwd_tail = len(fwd_r.tail) if fwd_r.binding is fwd_b else len(rev_r.tail)
        rev_tail = len(rev_r.tail) if rev_r.binding is rev_b else len(fwd_r.tail)
        length, mode, ok = _product(fwd_b, rev_b, len(template), circular, fwd_tail, rev_tail)
        if ok:
            product_len = length
        else:
            notes.append("선형 주형에서 프라이머가 서로 반대 방향을 향합니다 — 산물이 생기지 않습니다.")

    has_tail = any(r.tail for r in reports[:2])
    tms_anneal = [r.tm_anneal for r in reports[:2] if not math.isnan(r.tm_anneal)]
    tms_full = [r.tm_full for r in reports[:2] if not math.isnan(r.tm_full)]
    if not tms_anneal:
        result["program"] = None
        result["notes"] = notes + ["Tm을 계산할 수 없습니다 (염기에 ACGT 외 문자가 있는지 확인하세요)."]
        return result

    def ta(tms: list[float]) -> float:
        return round(min(max(min(tms) - c.ta_offset, c.ta_min), c.ta_max), 1)

    ta_stage1 = ta(tms_anneal)
    ta_stage2 = ta(tms_full) if tms_full else ta_stage1

    if mode == "whole_plasmid":
        cycles = c.sdm_cycles
        notes.append("프라이머가 바깥쪽을 향하고 산물이 플라스미드 전체 길이와 비슷합니다 — "
                     "whole-plasmid site-directed mutagenesis (inverse PCR)로 계산했습니다. "
                     "PCR 후 DpnI 처리(37 °C 1시간)로 주형을 제거하고, 평활말단 라이게이션 또는 "
                     "In-Fusion/Gibson으로 환형화하세요. 5' 인산화 프라이머를 쓰면 "
                     "T4 ligase로 바로 연결할 수 있습니다.")
    else:
        cycles = c.cycles

    ext_len = product_len if product_len else None
    ext_s = (max(c.min_extension_s, c.extension_s_per_kb * ext_len / 1000.0)
             if ext_len else None)
    if ext_s is not None:
        ext_s = int(math.ceil(ext_s / 5.0) * 5)

    steps = [
        {"name": "Initial denaturation", "temp": 95, "time_s": 120, "cycles": 1},
        {"name": "Denaturation", "temp": 95, "time_s": 20, "cycles": cycles},
        {"name": "Annealing", "temp": ta_stage2, "time_s": 30, "cycles": cycles},
        {"name": "Extension", "temp": 72, "time_s": ext_s, "cycles": cycles},
        {"name": "Final extension", "temp": 72, "time_s": 300, "cycles": 1},
        {"name": "Hold", "temp": 4, "time_s": None, "cycles": 1},
    ]
    two_stage = None
    if has_tail and abs(ta_stage2 - ta_stage1) >= 2:
        two_stage = {
            "stage1": {"cycles": 5, "annealing_temp": ta_stage1,
                       "reason": "5' tail은 첫 사이클에서 주형에 결합하지 않으므로 "
                                 "annealing 부분의 Tm 기준으로 낮게 잡습니다."},
            "stage2": {"cycles": max(cycles - 5, 1), "annealing_temp": ta_stage2,
                       "reason": "2사이클 이후 산물에는 tail이 포함되므로 전체 프라이머 Tm 기준입니다."},
        }
        steps[2]["temp"] = ta_stage1
        steps[2]["cycles"] = 5
        steps.insert(3, {"name": "Annealing (stage 2)", "temp": ta_stage2,
                         "time_s": 30, "cycles": max(cycles - 5, 1)})

    result.update({
        "mode": mode,
        "product_length": product_len,
        "annealing_temp": ta_stage2,
        "two_stage": two_stage,
        "program": steps,
        "mix": reaction_mix(c),
        "notes": notes,
    })
    return result


def reaction_mix(c: Conditions) -> dict[str, Any]:
    """Pfu-X 2x premix based reaction, scaled to the requested volume."""
    scale = c.reaction_uL / 50.0
    rows = [
        {"component": "2x Pfu-X premix (dNTP·Mg²⁺ 포함)", "volume_uL": round(25.0 * scale, 1),
         "final": "1x"},
        {"component": f"Forward primer (10 µM)", "volume_uL": round(1.25 * scale, 2),
         "final": f"{c.primer_conc_nM:.0f} nM"},
        {"component": f"Reverse primer (10 µM)", "volume_uL": round(1.25 * scale, 2),
         "final": f"{c.primer_conc_nM:.0f} nM"},
        {"component": "Template DNA (plasmid)", "volume_uL": "1",
         "final": "10-50 ng (plasmid) / 50-100 ng (genomic)"},
        {"component": "Nuclease-free water", "volume_uL": "to volume",
         "final": f"{c.reaction_uL:.0f} µL"},
    ]
    return {"total_uL": c.reaction_uL, "rows": rows,
            "note": "2x premix가 아닌 낱개 효소를 쓰는 경우 10x buffer 5 µL, dNTP 각 200 µM, "
                    "Pfu-X 1.25 U, 나머지는 물로 50 µL를 맞추세요."}


ASSUMPTIONS = {
    "tm": "SantaLucia 1998 unified nearest-neighbour 파라미터, "
          "염 보정은 0.368·(N-1)·ln[Na⁺]eq, [Na⁺]eq = [Na⁺] + 120·√([Mg²⁺]-[dNTP]) "
          "(von Ahsen 2001). 기본값: primer 250 nM, Na⁺ 10 mM, Mg²⁺ 2 mM, dNTP 0.2 mM.",
    "annealing": "Ta = min(Tm_fwd, Tm_rev) − 5 °C, 50-68 °C로 제한. 5' tail이 있는 "
                 "프라이머는 주형에 결합하는 3' 부분의 Tm을 먼저 적용하는 2단계 프로그램을 제안합니다.",
    "extension": "72 °C에서 산물 1 kb당 30초(최소 30초), 5초 단위 반올림. Pfu-X는 proofreading "
                 "효소로 Pfu(1 kb/분)보다 빠른 신장 속도를 가정했습니다.",
    "cycles": "일반 클로닝 PCR 30 사이클, whole-plasmid site-directed mutagenesis 18 사이클.",
    "caveat": "모든 값은 Solgent Pfu-X 범용 프로토콜을 바탕으로 한 계산상의 출발점입니다. "
              "실제 반응은 주형·프라이머에 따라 최적화가 필요하며, 경계선상의 Ta는 "
              "gradient PCR로 확인하는 것을 권합니다.",
}
