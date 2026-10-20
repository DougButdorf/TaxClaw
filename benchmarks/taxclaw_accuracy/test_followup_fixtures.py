"""Contract checks for the separate changed-form corpus; no model calls."""
import json
import re
import tempfile
import unittest
from pathlib import Path

import pymupdf

from src.extract import schema_for
from .fixtures import _specs as original_specs
from .followup_fixtures import CORPUS_ID, SCAN_PARAMETERS, _specs, build_fixtures
from .grader import flatten, normalized, score


class FollowupFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="taxclaw-followup-test-")
        cls.directory = Path(cls.temp.name)
        cls.records = build_fixtures(cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_manifest_pairs_page_counts_and_separate_namespace(self):
        self.assertEqual(len(self.records), 8)
        self.assertEqual(sum(x["page_count"] for x in self.records), 10)
        self.assertEqual(json.loads((self.directory / "manifest.json").read_text()), self.records)
        self.assertEqual({x["corpus_id"] for x in self.records}, {CORPUS_ID})
        self.assertEqual(len({x["fixture_id"] for x in self.records}), 8)
        for typ in ("1099-R", "1099-G", "1099-K", "K-1"):
            clean, scan = [x for x in self.records if x["doc_type"] == typ]
            self.assertEqual((clean["variant"], scan["variant"]), ("clean", "degraded_scan"))
            self.assertEqual(clean["expected"], scan["expected"])
            self.assertEqual(clean["field_types"], scan["field_types"])
            self.assertEqual(scan["generation"]["scan_parameters"], SCAN_PARAMETERS)
            self.assertTrue(clean["fixture_id"].startswith("wp_f_changed_"))

    def test_current_schema_and_all_leaf_types(self):
        counts = {}
        for record in self.records:
            expected = record["expected"]
            schema = schema_for(record["doc_type"])
            self.assertEqual(set(expected), set(schema["properties"]))
            counts[record["doc_type"]] = len(expected)
            self.assertEqual(set(flatten(expected)), set(record["field_types"]))
            for key, value in expected.items():
                actual_type = "null" if value is None else "boolean" if type(value) is bool else "object" if isinstance(value, dict) else "string"
                self.assertIn(actual_type, schema["properties"][key]["type"], key)
            for path, value in flatten(expected).items():
                normalized(value, record["field_types"][path])
            self.assertTrue(score(expected, expected, record["field_types"])["exact_document"])
        self.assertEqual(counts, {"1099-R": 30, "1099-G": 18, "1099-K": 26, "K-1": 33})

    def test_scans_are_image_only_clean_has_human_labels(self):
        for record in self.records:
            with pymupdf.open(self.directory / record["pdf_path"]) as doc:
                self.assertEqual(len(doc), record["page_count"])
                text = "\n".join(page.get_text() for page in doc)
                if record["variant"] == "degraded_scan":
                    self.assertEqual(text.strip(), "")
                    for page in doc:
                        self.assertEqual(len(page.get_images()), 1)
                        self.assertEqual(page.get_fonts(), [])
                else:
                    self.assertIn("SYNTHETIC NOT FOR FILING", text)
                    self.assertIn("42 Fictional Quay", text)
                    self.assertNotIn("fatca_filing_requirement", text)
                    self.assertNotIn("FATCA filing requirement", text)
                    # Canonical machine keys are not visible labels or metadata.
                    for key in record["expected"]:
                        if "_" in key:
                            self.assertNotIn(key, text)
                            self.assertNotIn(key, str(doc.metadata))
                    if record["doc_type"] == "1099-K":
                        self.assertIn("FILER'S name", text)
                        self.assertIn("PAYEE'S name", text)
                    if record["doc_type"] == "1099-R":
                        self.assertIn("7Q", text)
                        self.assertIn("QO Example District", text)

    def test_byte_identical_rebuild(self):
        with tempfile.TemporaryDirectory(prefix="taxclaw-followup-rebuild-") as second:
            other = Path(second)
            self.assertEqual(build_fixtures(other), self.records)
            for path in self.directory.iterdir():
                self.assertEqual(path.read_bytes(), (other / path.name).read_bytes(), path.name)

    def test_k1_coded_keys_continue_across_pages_and_missing_objects(self):
        pages = next(pages for typ, _, pages in _specs() if typ == "K-1")
        first = {x.path for x in pages[0]}
        second = {x.path for x in pages[1]}
        self.assertIn("other_deductions.13W", first)
        self.assertIn("other_deductions.13H", second)
        self.assertIn("other_deductions.13A", second)
        self.assertIn("other_information.20A", first)
        self.assertIn("other_information.20Z", second)
        record = next(x for x in self.records if x["doc_type"] == "K-1")
        self.assertIsNone(record["expected"]["other_income"])
        self.assertIsNone(record["expected"]["foreign_taxes_paid"])
        self.assertEqual(record["expected"]["other_information"]["20Z"], "STMT")
        self.assertEqual(record["expected"]["other_deductions"]["13A"],
                         record["expected"]["charitable_contributions"])
        for value in record["expected"].values():
            if isinstance(value, dict):
                self.assertTrue(all(re.fullmatch(r"\d+[A-Z]+", key) for key in value))

    def test_original_r_and_k1_values_preserved_except_explicit_code_expansion(self):
        originals = {typ: pages for typ, _, pages, _ in original_specs() if typ in {"1099-R", "K-1"}}
        for record in self.records:
            if record["variant"] != "clean" or record["doc_type"] not in originals:
                continue
            actual = flatten(record["expected"])
            for page in originals[record["doc_type"]]:
                for field in page:
                    path = field.path
                    if path == "distribution_code":
                        self.assertEqual(actual["distribution_codes"], field.value + "Q")
                        continue
                    if "." in path:
                        head, code = path.split(".")
                        prefix = {"other_deductions": 13, "other_credits": 15,
                                  "foreign_transactions": 16, "amt_items": 17,
                                  "other_information": 20}[head]
                        path = f"{head}.{prefix}{code}"
                    self.assertEqual(actual[path], field.value, path)


if __name__ == "__main__":
    unittest.main()
