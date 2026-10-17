"""Layout maths behind the Tk widgets, checked without a display."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import view_model as vm  # noqa: E402
from app.pcr import design_pcr  # noqa: E402
from app.snapgene import SnapGeneFile  # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "pET28a-6xHis-hPRD_ORF1_only.dna")


class TestSequenceRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plasmid = SnapGeneFile.read(EXAMPLE)

    def test_every_base_appears_once(self):
        rows = vm.sequence_rows(self.plasmid.sequence, [], show_tracks=False)
        joined = "".join(r["text"][r["gutter"]:].replace(" ", "")
                         for r in rows if r["kind"] == "sequence")
        self.assertEqual(joined, self.plasmid.sequence)

    def test_lines_cover_the_sequence(self):
        rows = [r for r in vm.sequence_rows(self.plasmid.sequence, [], show_tracks=False)
                if r["kind"] == "sequence"]
        self.assertEqual(rows[0]["first"], 1)
        self.assertEqual(rows[-1]["last"], len(self.plasmid.sequence))

    def test_track_rows_name_the_features_they_cross(self):
        rows = vm.sequence_rows(self.plasmid.sequence, self.plasmid.features)
        names = {r.get("feature") for r in rows if r["kind"] == "track"}
        self.assertIn("SCOTIN PRD", names)
        self.assertIn("KanR", names)

    def test_track_bar_lines_up_with_the_bases(self):
        prd = next(f for f in self.plasmid.features if f.name == "SCOTIN PRD")
        rows = vm.sequence_rows(self.plasmid.sequence, [prd])
        track = next(r for r in rows if r["kind"] == "track" and r["first"] <= prd.start
                     <= r["last"])
        column = vm.column_of(prd.start - track["first"], track["gutter"])
        self.assertEqual(track["text"][column], "├")

    def test_complement_rows_are_optional(self):
        plain = vm.sequence_rows("ACGTACGTAC", [], show_complement=False, show_tracks=False)
        both = vm.sequence_rows("ACGTACGTAC", [], show_complement=True, show_tracks=False)
        self.assertEqual(len(plain), 1)
        self.assertEqual(len(both), 2)
        self.assertTrue(both[1]["text"].strip().startswith("TGCATGCATG"))


class TestMapArcs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plasmid = SnapGeneFile.read(EXAMPLE)

    def test_one_arc_per_feature(self):
        arcs = vm.map_arcs(self.plasmid.features, len(self.plasmid.sequence))
        self.assertEqual(len(arcs), len(self.plasmid.features))

    def test_no_two_features_share_a_ring_where_they_overlap(self):
        arcs = vm.map_arcs(self.plasmid.features, len(self.plasmid.sequence))
        for i, a in enumerate(arcs):
            for b in arcs[i + 1:]:
                if a["ring"] == b["ring"]:
                    self.assertFalse(a["start"] <= b["end"] and b["start"] <= a["end"],
                                     f"{a['name']} overlaps {b['name']} in ring {a['ring']}")

    def test_duplicate_features_land_on_separate_rings(self):
        """The file carries KanR twice over the same span."""
        kan = [a for a in vm.map_arcs(self.plasmid.features, len(self.plasmid.sequence))
               if a["name"] == "KanR"]
        self.assertEqual(len(kan), 2)
        self.assertNotEqual(kan[0]["ring"], kan[1]["ring"])

    def test_position_one_starts_at_the_top(self):
        arcs = vm.map_arcs(self.plasmid.features, 1000)
        for arc in arcs:
            self.assertLessEqual(arc["extent"], 0)      # clockwise
            self.assertLessEqual(arc["start_angle"], 90.0)

    def test_white_features_get_a_visible_colour(self):
        self.assertNotEqual(vm.display_color("#ffffff"), "#ffffff")
        self.assertEqual(vm.display_color("#3366ff"), "#3366ff")


class TestReports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plasmid = SnapGeneFile.read(EXAMPLE)

    def test_feature_detail_carries_the_qualifiers(self):
        prd = next(f for f in self.plasmid.features if f.name == "SCOTIN PRD")
        text = vm.feature_detail(prd)
        self.assertIn("5,197–5,541", text)
        self.assertIn("CFTCSCCC", text)
        thrombin = next(f for f in self.plasmid.features if f.name == "thrombin site")
        self.assertIn("thrombin recognition and cleavage site", vm.feature_detail(thrombin))

    def test_pcr_report_covers_program_mix_and_assumptions(self):
        result = design_pcr(
            [{"name": "T7", "sequence": "CCCGCGAAATTAATACGACTCAC"},
             {"name": "RK rev", "sequence": "CTTTGGCTTCTTGCACGTCTTGTAAAG"}],
            self.plasmid.sequence, True, None)
        text = vm.pcr_report(result)
        self.assertIn("Annealing", text)
        self.assertIn("반응 믹스", text)
        self.assertIn("계산 근거와 가정", text)
        self.assertIn("Initial denaturation", text)

    def test_pcr_report_handles_a_single_primer(self):
        result = design_pcr([{"name": "T7", "sequence": "CCCGCGAAATTAATACGACTCAC"}],
                            self.plasmid.sequence, True, None)
        self.assertIn("프라이머 2개가 필요합니다", vm.pcr_report(result))


if __name__ == "__main__":
    unittest.main()
