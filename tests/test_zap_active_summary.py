import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dvwa"))
from summarize_zap_active import summarize


class ZapActiveSummaryTests(unittest.TestCase):
    def test_unattributed_har_input_observations_are_reported_without_values(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            root = Path(directory)
            report = root / "report.json"
            har = root / "traffic.har"
            log = root / "zap.log"
            report.write_text(json.dumps({"site": []}), encoding="utf-8")
            har.write_text(json.dumps({"log": {"entries": [
                {"request": {"method": "POST", "url": "http://dvwa/vulnerabilities/sqli/",
                              "headers": [], "queryString": [],
                              "postData": {"params": [{"name": "id", "value": "PRIVATE_SENTINEL"}]}}},
                {"request": {"method": "POST", "url": "http://dvwa/vulnerabilities/sqli_blind/",
                              "headers": [{"name": "X-ZAP-Scan-ID", "value": "40018"}],
                              "queryString": [],
                              "postData": {"params": [{"name": "id", "value": "1"}]}}},
            ]}}), encoding="utf-8")
            log.write_text(
                "Generic SQL injection rule sent requests [2 >= 1]\n"
                "MySQL timing SQL injection rule sent requests [1 >= 1]\n",
                encoding="utf-8")

            result = summarize(report, har, log, "medium")

        observations = result["har_input_coordinate_observations_any_job"]
        self.assertEqual(observations, [
            {"path": "/vulnerabilities/sqli/", "method": "POST",
             "parameter_present": True, "request_count": 1},
            {"path": "/vulnerabilities/sqli_blind/", "method": "POST",
             "parameter_present": True, "request_count": 1},
        ])
        self.assertEqual(result["coordinate_coverage"], {"observed": 1, "expected": 2, "complete": False})
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
