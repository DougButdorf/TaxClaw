"""Focused full-corpus provenance/coverage checks; no inference or network."""
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

import pymupdf

from . import fixtures, followup_fixtures
from .full_fixtures import CORPUS_ID, build_fixtures
from .grader import flatten, score


class FullFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="taxclaw-full-test-")
        cls.directory = Path(cls.temp.name)
        cls.records = build_fixtures(cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_original_twelve_included_plus_g_k_and_exact_pair_counts(self):
        original_types = {typ for typ, *_ in fixtures._specs()}
        self.assertEqual(len(original_types), 12)
        self.assertEqual({r["doc_type"] for r in self.records}, original_types | {"1099-G", "1099-K"})
        self.assertEqual(len(self.records), 28)
        self.assertEqual(sum(r["page_count"] for r in self.records), 32)
        self.assertEqual(len({r["fixture_id"] for r in self.records}), 28)
        self.assertEqual({r["corpus_id"] for r in self.records}, {CORPUS_ID})
        self.assertEqual(json.loads((self.directory / "manifest.json").read_text()), self.records)
        self.assertEqual(len(list(self.directory.iterdir())), 29)
        for typ in original_types | {"1099-G", "1099-K"}:
            clean, scan = [r for r in self.records if r["doc_type"] == typ]
            self.assertEqual((clean["variant"], scan["variant"]), ("clean", "degraded_scan"))
            self.assertEqual(clean["expected"], scan["expected"])
            self.assertEqual(clean["field_types"], scan["field_types"])
            self.assertEqual(clean["page_count"], scan["page_count"])
            self.assertEqual(set(flatten(clean["expected"])), set(clean["field_types"]))
            self.assertTrue(score(clean["expected"], clean["expected"], clean["field_types"])["exact_document"])

    def test_corrected_r_and_k1_keys(self):
        r = next(r["expected"] for r in self.records if r["doc_type"] == "1099-R")
        self.assertNotIn("distribution_code", r)
        self.assertEqual(r["distribution_codes"], "7Q")
        self.assertIsNone(r["fatca_filing_requirement"])
        k1 = next(r["expected"] for r in self.records if r["doc_type"] == "K-1")
        self.assertEqual(k1["other_deductions"]["13W"], "87.65")
        self.assertEqual(k1["other_deductions"]["13A"], k1["charitable_contributions"])
        self.assertEqual(k1["other_information"]["20Z"], "STMT")
        for value in k1.values():
            if isinstance(value, dict):
                self.assertTrue(all(re.fullmatch(r"\d+[A-Z]+", key) for key in value))

    def test_image_only_scans_and_pdf_hashes(self):
        for record in self.records:
            data = (self.directory / record["pdf_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), record["generation"]["pdf_sha256"])
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                self.assertEqual(len(doc), record["page_count"])
                if record["variant"] == "degraded_scan":
                    self.assertEqual(record["generation"]["scan_parameters"], followup_fixtures.SCAN_PARAMETERS)
                    for page in doc:
                        self.assertEqual(page.get_text().strip(), "")
                        self.assertEqual(len(page.get_images()), 1)
                        self.assertEqual(page.get_fonts(), [])
                else:
                    self.assertIn("SYNTHETIC NOT FOR FILING", doc[0].get_text())

    def test_verbatim_sources_and_expected_values(self):
        with tempfile.TemporaryDirectory(prefix="taxclaw-full-provenance-") as temporary:
            root = Path(temporary)
            original = fixtures.build_fixtures(root / "original")
            followup = followup_fixtures.build_fixtures(root / "followup")
            changed = {r["doc_type"] for r in followup}
            for record in self.records:
                module = followup_fixtures if record["doc_type"] in changed else fixtures
                source_dir = root / ("followup" if module is followup_fixtures else "original")
                sources = followup if module is followup_fixtures else original
                source = next(r for r in sources if r["doc_type"] == record["doc_type"]
                              and (module is fixtures or r["variant"] == record["variant"]))
                self.assertEqual(source["expected"], record["expected"])
                self.assertEqual(source["field_types"], record["field_types"])
                self.assertEqual(record["generation"]["source_module_sha256"],
                                 hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())
                source_bytes = (source_dir / source["pdf_path"]).read_bytes()
                self.assertEqual(record["generation"]["source_pdf_sha256"], hashlib.sha256(source_bytes).hexdigest())
                if record["variant"] == "clean" or module is followup_fixtures:
                    self.assertEqual(source_bytes, (self.directory / record["pdf_path"]).read_bytes())

    def test_deterministic_twice(self):
        with tempfile.TemporaryDirectory(prefix="taxclaw-full-rebuild-") as temporary:
            second = Path(temporary)
            self.assertEqual(build_fixtures(second), self.records)
            self.assertEqual({p.name for p in second.iterdir()}, {p.name for p in self.directory.iterdir()})
            for path in self.directory.iterdir():
                self.assertEqual(path.read_bytes(), (second / path.name).read_bytes(), path.name)


if __name__ == "__main__":
    unittest.main()
