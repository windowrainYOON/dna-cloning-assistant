"""Tm, binding-site and Pfu-X program tests, using the reference plasmid."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pcr import Conditions, design_pcr, find_binding, gc_percent, tm_nearest_neighbour  # noqa: E402
from app.snapgene import SnapGeneFile  # noqa: E402

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "examples", "pET28a-6xHis-hPRD_ORF1_only.dna")

T7 = "CCCGCGAAATTAATACGACTCAC"
SACI_REV = ("CGACGGAGCTCGAATTACTTGTCGTCATCGTCTTTGTAGTCaccggagcctccgccacc"
            "GAGGGCCGCCTTCG")
RK_FWD = "AAGAAGCCAAAGCCGGTTGTCACCAC"
RK_REV = "CTTTGGCTTCTTGCACGTCTTGTAAAG"


class TestTm(unittest.TestCase):
    def test_known_oligo(self):
        # 20-mer, 50% GC; published NN Tm at 0.25 uM primer / ~50 mM Na+ is ~56-58 C.
        tm = tm_nearest_neighbour("ACGTACGTACGTAGCTAGCT",
                                  Conditions(na_mM=50, mg_mM=0, dntp_mM=0))
        self.assertTrue(50 < tm < 62, tm)

    def test_longer_is_hotter(self):
        c = Conditions()
        self.assertLess(tm_nearest_neighbour("ACGTACGTACGTAC", c),
                        tm_nearest_neighbour("ACGTACGTACGTACGTACGTAC", c))

    def test_gc_raises_tm(self):
        c = Conditions()
        self.assertLess(tm_nearest_neighbour("ATATATATATATATATATAT", c),
                        tm_nearest_neighbour("GCGCGCGCGCGCGCGCGCGC", c))

    def test_gc_percent(self):
        self.assertAlmostEqual(gc_percent("GGCCAATT"), 50.0)


class TestBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plasmid = SnapGeneFile.read(EXAMPLE)

    def _bind(self, primer):
        return find_binding(primer, self.plasmid.sequence, self.plasmid.is_circular)

    def test_t7_primer_matches_snapgene(self):
        b = self._bind(T7)
        self.assertIsNotNone(b)
        self.assertEqual(b.strand, 0)
        # SnapGene annotates 4973-4995; its primer locations run one lower
        # than the feature coordinates this tool uses throughout.
        self.assertEqual((b.start, b.end), (4974, 4996))
        self.assertEqual(b.matched_len, len(T7))
        self.assertEqual(b.tail, "")

    def test_tailed_primer_reports_its_tail(self):
        b = self._bind(SACI_REV)
        self.assertIsNotNone(b)
        self.assertEqual(b.strand, 1)
        self.assertEqual((b.start, b.end), (5525, 5538))   # SnapGene: 5524-5537
        self.assertEqual(b.matched_len, 14)
        self.assertGreater(b.tail_mismatches, 0)
        self.assertTrue(b.tail.upper().endswith("ACCGGAGCCTCCGCCACC"))

    def test_mutagenesis_pair_points_outward(self):
        fwd, rev = self._bind(RK_FWD), self._bind(RK_REV)
        self.assertEqual(fwd.strand, 0)
        self.assertEqual(rev.strand, 1)
        # SnapGene annotates 5247-5260 (fwd) and 5220-5234 (rev): back to back,
        # so on the circle the forward primer starts downstream of the reverse one.
        self.assertEqual((fwd.start, fwd.end), (5248, 5261))   # SnapGene: 5247-5260
        self.assertEqual((rev.start, rev.end), (5221, 5235))   # SnapGene: 5220-5234
        self.assertGreater(fwd.start, rev.end)


class TestProgram(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plasmid = SnapGeneFile.read(EXAMPLE)

    def _design(self, fwd, rev, **conditions):
        return design_pcr([{"name": "fwd", "sequence": fwd}, {"name": "rev", "sequence": rev}],
                          self.plasmid.sequence, self.plasmid.is_circular, conditions or None)

    def test_cloning_amplicon(self):
        res = self._design(T7, SACI_REV)
        self.assertEqual(res["mode"], "amplicon")
        # T7 primer starts at 4973, tailed reverse primer ends at 5554 plus its tail.
        self.assertEqual(res["product_length"], 624)   # 565 bp core + 59 nt tail
        self.assertTrue(50 <= res["annealing_temp"] <= 68)
        ext = next(s for s in res["program"] if s["name"] == "Extension")
        self.assertEqual(ext["time_s"], 30)          # <1 kb -> the 30 s floor
        self.assertIsNotNone(res["two_stage"])       # the reverse primer has a tail

    def test_whole_plasmid_mutagenesis(self):
        res = self._design(RK_FWD, RK_REV)
        self.assertEqual(res["mode"], "whole_plasmid")
        self.assertEqual(res["product_length"], 5729)  # whole plasmid + both tails
        ext = next(s for s in res["program"] if s["name"] == "Extension")
        self.assertEqual(ext["time_s"], 175)         # 5.7 kb at 30 s/kb, to the next 5 s
        cycles = next(s for s in res["program"] if s["name"] == "Denaturation")["cycles"]
        self.assertEqual(cycles, 18)
        self.assertTrue(any("DpnI" in n for n in res["notes"]))

    def test_annealing_follows_the_cooler_primer(self):
        res = self._design(T7, SACI_REV, ta_offset=5)
        tms = [p["tm_anneal"] for p in res["primers"]]
        anneal = next(s for s in res["program"] if s["name"] == "Annealing")
        self.assertAlmostEqual(anneal["temp"], round(min(tms) - 5, 1), places=1)

    def test_single_primer_has_no_program(self):
        res = design_pcr([{"name": "fwd", "sequence": T7}], self.plasmid.sequence, True, None)
        self.assertIsNone(res["program"])
        self.assertEqual(len(res["primers"]), 1)

    def test_conditions_are_echoed_and_applied(self):
        hot = self._design(T7, SACI_REV, ta_offset=0)
        cool = self._design(T7, SACI_REV, ta_offset=10)
        self.assertGreater(hot["annealing_temp"], cool["annealing_temp"])
        self.assertEqual(hot["conditions"]["ta_offset"], 0)

    def test_mix_scales_with_volume(self):
        res = self._design(T7, SACI_REV, reaction_uL=25)
        premix = res["mix"]["rows"][0]
        self.assertEqual(premix["volume_uL"], 12.5)


if __name__ == "__main__":
    unittest.main()
