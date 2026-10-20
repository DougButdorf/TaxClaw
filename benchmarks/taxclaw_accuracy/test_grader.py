import unittest

from .grader import score


class GraderTests(unittest.TestCase):
    def test_missing_null_zero_are_distinct(self):
        key = {"blank": None, "zero": "0.00"}
        types = {"zero": "money"}
        self.assertEqual(score(key, {"zero": "0"}, types)["correct"], 1)
        self.assertEqual(score(key, {"blank": "", "zero": None}, types)["correct"], 0)
        self.assertTrue(score(key, {"blank": None, "zero": 0}, types)["exact_document"])

    def test_money_sign_and_precision(self):
        self.assertTrue(score({"a": "-1234.56"}, {"a": "($1,234.56)"},
                              {"a": "money"})["exact_document"])
        self.assertFalse(score({"a": "12.34"}, {"a": "12.35"},
                               {"a": "money"})["exact_document"])

    def test_identifier_leading_zero_and_masks(self):
        types = {"ssn": "identifier"}
        self.assertTrue(score({"ssn": "000-00-1234"}, {"ssn": "000001234"}, types)["exact_document"])
        self.assertFalse(score({"ssn": "000-00-1234"}, {"ssn": "1234"}, types)["exact_document"])
        self.assertFalse(score({"ssn": "XXX-XX-1234"}, {"ssn": "000-00-1234"}, types)["exact_document"])

    def test_transactions_extra_rows_and_objects(self):
        gold = {"rows": [{"basis": "10.00"}], "codes": {"D": "2.00"}}
        actual = {"rows": [{"basis": "10"}, {"basis": "20"}], "codes": {"D": "2"}}
        report = score(gold, actual, {"rows.0.basis": "money", "codes.D": "money"})
        self.assertEqual(report["accuracy"], 1)
        self.assertFalse(report["exact_document"])
        self.assertEqual(report["extra_fields"], ["rows.1.basis"])

    def test_booleans_and_dates(self):
        gold = {"reported": False, "sold": "2025-10-20"}
        types = {"reported": "boolean", "sold": "date"}
        self.assertTrue(score(gold, {"reported": False, "sold": "10/20/2025"}, types)["exact_document"])
        self.assertFalse(score(gold, {"reported": 0, "sold": "10/20/2025"}, types)["exact_document"])

    def test_malformed_and_nonfinite(self):
        self.assertEqual(score({"a": "1"}, [1], {"a": "number"})["correct"], 0)
        self.assertFalse(score({"a": "1"}, {"a": "NaN"}, {"a": "number"})["exact_document"])

    def test_object_is_not_transaction_array(self):
        report = score({"rows": [{"basis": "10.00"}]},
                       {"rows": {"0": {"basis": "10"}}}, {"rows.0.basis": "money"})
        self.assertEqual(report["correct"], 0)
        self.assertEqual(report["shape_errors"], ["rows"])
        self.assertFalse(report["exact_document"])


if __name__ == "__main__":
    unittest.main()
