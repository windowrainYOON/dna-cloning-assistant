"""Round-trip and parsing tests against the reference plasmid."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.snapgene import SnapGeneFile  # noqa: E402

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "examples", "pET28a-6xHis-hPRD_ORF1_only.dna")


class TestParse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = SnapGeneFile.read(EXAMPLE)

    def test_sequence(self):
        # 5,717 bp circular; the T7 terminator ends at 5,692, which is where
        # the "5692 bp" figure in the lab notes comes from.
        self.assertEqual(len(self.f.sequence), 5717)
        self.assertTrue(self.f.is_circular)
        self.assertEqual(set(self.f.sequence) - set("ACGT"), set())

    def test_feature_count_and_positions(self):
        self.assertEqual(len(self.f.features), 17)
        by_name = {}
        for feat in self.f.features:
            by_name.setdefault(feat.name, []).append(feat)
        for name in ("T7 promoter", "lac operator", "RBS", "6xHis", "thrombin site",
                     "TEV site", "SCOTIN PRD", "KanR", "lacI", "ori", "f1 ori", "rop",
                     "bom", "T7 terminator"):
            self.assertIn(name, by_name, name)
        self.assertEqual((by_name["T7 promoter"][0].start, by_name["T7 promoter"][0].end),
                         (4984, 5002))
        self.assertEqual((by_name["6xHis"][0].start, by_name["6xHis"][0].end), (5083, 5100))
        self.assertEqual((by_name["TEV site"][0].start, by_name["TEV site"][0].end),
                         (5176, 5196))
        prd = by_name["SCOTIN PRD"][0]
        self.assertEqual((prd.start, prd.end), (5197, 5541))
        self.assertTrue(prd.translation.startswith("CFTCSCCC"))

    def test_primers(self):
        names = {p.name for p in self.f.primers}
        self.assertEqual(names, {"T7 (pET28a)", "SacI-FLAG-GGGSG-hPRD-rev",
                                 "PRD RK fwd", "PRD RK rev"})

    def test_cds_translations_match_sequence(self):
        """Every forward CDS feature translates to its stored protein."""
        table = _codon_table()
        for feat in self.f.features:
            if feat.type != "CDS" or feat.directionality != 1 or not feat.translation:
                continue
            dna = self.f.subsequence(feat.start, feat.end)
            protein = "".join(table.get(dna[i:i + 3], "?") for i in range(0, len(dna) - 2, 3))
            self.assertEqual(protein, feat.translation, feat.name)


class TestRoundTrip(unittest.TestCase):
    def test_reparse_is_stable(self):
        original = SnapGeneFile.read(EXAMPLE)
        again = SnapGeneFile.read(original.to_bytes())
        self.assertEqual(again.sequence, original.sequence)
        self.assertEqual(again.is_circular, original.is_circular)
        self.assertEqual(len(again.features), len(original.features))
        self.assertEqual([(f.name, f.start, f.end) for f in again.features],
                         [(f.name, f.start, f.end) for f in original.features])
        self.assertEqual([(p.name, p.sequence) for p in again.primers],
                         [(p.name, p.sequence) for p in original.primers])
        self.assertEqual(again.notes.get("UUID"), original.notes.get("UUID"))


class TestEdit(unittest.TestCase):
    def setUp(self):
        self.f = SnapGeneFile.read(EXAMPLE)

    def test_insert_shifts_downstream_features(self):
        prd_before = next(f for f in self.f.features if f.name == "SCOTIN PRD")
        start, end = prd_before.start, prd_before.end
        self.f.apply_edit(100, 102, "AAAAAA")  # 3 bp -> 6 bp, +3
        prd_after = next(f for f in self.f.features if f.name == "SCOTIN PRD")
        self.assertEqual((prd_after.start, prd_after.end), (start + 3, end + 3))
        self.assertEqual(len(self.f.sequence), 5720)

    def test_deleting_a_feature_removes_it(self):
        prd = next(f for f in self.f.features if f.name == "SCOTIN PRD")
        self.f.apply_edit(prd.start, prd.end, "")
        self.assertNotIn("SCOTIN PRD", [f.name for f in self.f.features])
        self.assertEqual(len(self.f.sequence), 5717 - (prd.end - prd.start + 1))

    def test_edit_survives_a_write(self):
        self.f.apply_edit(5197, 5199, "GGG")
        again = SnapGeneFile.read(self.f.to_bytes())
        self.assertEqual(again.sequence[5196:5199], "GGG")
        self.assertEqual(len(again.features), len(self.f.features))


def _codon_table():
    bases = "TCAG"
    aminos = ("FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG")
    return {a + b + c: aminos[i]
            for i, (a, b, c) in enumerate((x, y, z) for x in bases for y in bases for z in bases)}


if __name__ == "__main__":
    unittest.main()
