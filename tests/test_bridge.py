import os
import unittest

os.environ["MOCK"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
import bridge  # noqa: E402
from etabs_client import EtabsError, parse_table_response  # noqa: E402


class BridgeMockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(bridge.app)

    def setUp(self):
        bridge._client = None

    def test_health_and_status(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        status = self.client.get("/status").json()
        self.assertTrue(status["connected"])
        self.assertTrue(status["mock"])
        self.assertIn("MOCK_Building.edb", status["model_file"])

    def test_list_tables_and_load_dynamic_table(self):
        response = self.client.get("/tables")
        self.assertEqual(response.status_code, 200)
        table_names = response.json()["tables"]
        self.assertGreaterEqual(len(table_names), 1)
        table = self.client.get("/table/" + table_names[0].replace(" ", "%20"))
        self.assertEqual(table.status_code, 200)
        self.assertEqual(table.json()["columns"][0], "UniqueName")
        self.assertGreaterEqual(len(table.json()["rows"]), 1)

    def test_select_valid_and_failed_names(self):
        response = self.client.post("/select", json={"element_ids": ["F101", "NOPE"], "element_type": "frame", "clear_first": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected_count"], 1)
        self.assertEqual(response.json()["failed_names"], ["NOPE"])

    def test_save_group(self):
        response = self.client.post("/group", json={"group_name": "Review Set", "element_ids": ["F101"], "element_type": "frame"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assigned_count"], 1)
        self.assertEqual(response.json()["group_name"], "Review Set")

    def test_refresh_view(self):
        response = self.client.post("/refresh_view")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["refreshed"])

    def test_invalid_element_type_rejected_by_request_schema(self):
        response = self.client.post("/select", json={"element_ids": ["F101"], "element_type": "wall"})
        self.assertEqual(response.status_code, 422)

    def test_parse_flat_com_response_into_rows(self):
        # Mimics the six-item COM ref/out result shape without invoking real ETABS.
        response = ([], 1, ["UniqueName", "Story"], 2, ["F1", "Roof", "F2", "Level 1"], 0)
        self.assertEqual(parse_table_response("mock table", response), [
            {"UniqueName": "F1", "Story": "Roof"},
            {"UniqueName": "F2", "Story": "Level 1"},
        ])

    def test_table_response_checks_csi_return_code(self):
        response = ([], 1, ["UniqueName"], 1, ["F1"], 7)
        with self.assertRaisesRegex(EtabsError, "return code 7"):
            parse_table_response("mock table", response)


if __name__ == "__main__":
    unittest.main()
