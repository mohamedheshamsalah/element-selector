import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import apply_advanced_query, apply_conditions  # noqa: E402


class FilteringExamples(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "element": ["C1", "B1", "C2", "B2"],
            "type": ["Column", "Beam", "Column", "Beam"],
            "dc_ratio": [0.7, 1.1, 1.25, 0.9],
            "note": ["ok", "check", None, ""],
        })

    def test_numeric_and_text_conditions_with_and(self):
        result = apply_conditions(self.frame, [
            {"column": "dc_ratio", "operator": ">", "value": 1.0},
            {"column": "type", "operator": "equals", "value": "Column"},
        ], "AND")
        self.assertEqual(result["element"].tolist(), ["C2"])

    def test_or_conditions(self):
        result = apply_conditions(self.frame, [
            {"column": "type", "operator": "equals", "value": "Column"},
            {"column": "dc_ratio", "operator": ">", "value": 1.0},
        ], "OR")
        self.assertEqual(set(result["element"]), {"C1", "B1", "C2"})

    def test_empty_values(self):
        result = apply_conditions(self.frame, [{"column": "note", "operator": "is empty", "value": None}])
        self.assertEqual(result["element"].tolist(), ["C2", "B2"])

    def test_advanced_query(self):
        result = apply_advanced_query(self.frame, "dc_ratio > 1 and type == 'Column'")
        self.assertEqual(result["element"].tolist(), ["C2"])

    def test_advanced_query_with_spaced_column(self):
        frame = self.frame.rename(columns={"dc_ratio": "Demand Ratio"})
        result = apply_advanced_query(frame, "`Demand Ratio` > 1")
        self.assertEqual(result["element"].tolist(), ["B1", "C2"])

    def test_advanced_query_rejects_function_calls(self):
        with self.assertRaisesRegex(ValueError, "For safety"):
            apply_advanced_query(self.frame, "__import__('os').system('echo unsafe')")

    def test_unknown_column_is_clear(self):
        with self.assertRaisesRegex(ValueError, "Column not found"):
            apply_conditions(self.frame, [{"column": "missing", "operator": "=", "value": 2}])


if __name__ == "__main__":
    unittest.main()
