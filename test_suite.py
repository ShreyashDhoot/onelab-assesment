"""
test_suite.py
=============
Comprehensive test suite for the Payments Reconciliation Platform.

Tests:
1. Core normalization, extraction, and fee calculation functions.
2. Reconciliation engine multi-pass matching logic.
3. Accurate detection and classification of all 24 anomaly types.
4. Correct categorization into the 4 Gap Types + Unmatched totals.
5. Exact financial KPI arithmetic (Platform, Bank, Final Gap, Cutoff Gap).
6. 100% precision, recall, and accuracy benchmark against ground_truth.csv.
7. REST API endpoint implementations (/health, /api/reconcile-sample, /api/benchmark, /api/export, /api/reconcile).
"""

import os
import sys
import io
import json
import unittest
from pathlib import Path

import pandas as pd

from reconciliation_engine import (
    ReconciliationEngine,
    normalize_reference,
    extract_order_id,
    extract_batch_info,
    calc_expected_fee_net,
    ANOMALY_TO_GAP_TYPE,
    GAP_TYPE_TIMING,
    GAP_TYPE_AMOUNT,
    GAP_TYPE_STATUS,
    GAP_TYPE_OPERATIONAL,
    GAP_TYPE_UNMATCHED_PLATFORM,
    GAP_TYPE_UNMATCHED_BANK,
    GAP_TYPE_CLEAN
)
from app import ReconciliationHandler

BASE_DIR = Path(__file__).resolve().parent
PLATFORM_CSV = BASE_DIR / "platform_transactions.csv"
BANK_CSV = BASE_DIR / "bank_transactions.csv"
GROUND_TRUTH_CSV = BASE_DIR / "ground_truth.csv"

# ---------------------------------------------------------------------------
# 1. Unit Tests: Normalization, Extraction & Helpers
# ---------------------------------------------------------------------------
class TestHelperFunctions(unittest.TestCase):
    def test_normalize_reference(self):
        # Empty or None
        self.assertIsNone(normalize_reference(None))
        self.assertIsNone(normalize_reference(""))
        self.assertIsNone(normalize_reference("nan"))
        self.assertIsNone(normalize_reference("None"))

        # Clean standard UTR
        self.assertEqual(normalize_reference("123456789012"), "123456789012")
        self.assertEqual(normalize_reference("HDFCR12345678901"), "HDFCR12345678901")

        # Whitespace and lowercase
        self.assertEqual(normalize_reference("  axisr12345678901  "), "AXISR12345678901")
        self.assertEqual(normalize_reference("ICICR 1234 5678 901"), "ICICR12345678901")

        # UTR- prefix formatting
        self.assertEqual(normalize_reference("UTR-1234 5678 9012"), "123456789012")
        self.assertEqual(normalize_reference("UTR- 987654321098"), "987654321098")

    def test_extract_order_id(self):
        self.assertIsNone(extract_order_id(None))
        self.assertIsNone(extract_order_id(""))
        self.assertIsNone(extract_order_id("PAYGATE SETTLEMENT/UPI"))

        self.assertEqual(
            extract_order_id("PAYGATE SETTLEMENT/UPI/ORD-2026-100012"),
            "ORD-2026-100012"
        )
        self.assertEqual(
            extract_order_id("PAYGATE SETTLEMENT/CARD/ORD-2026-095431/PARTIAL"),
            "ORD-2026-095431"
        )

    def test_extract_batch_info(self):
        # From batch_id column
        b_id, count = extract_batch_info("PAYGATE BATCH SETTLEMENT/BATCH-20261106-01/3 TXNS", "BATCH-20261106-01")
        self.assertEqual(b_id, "BATCH-20261106-01")
        self.assertEqual(count, 3)

        # From narration when column is NaN
        b_id2, count2 = extract_batch_info("PAYGATE BATCH SETTLEMENT/BATCH-20261109-02/5 TXNS", None)
        self.assertEqual(b_id2, "BATCH-20261109-02")
        self.assertEqual(count2, 5)

    def test_calc_expected_fee_net(self):
        # 2% MDR fee + 18% GST on fee
        # Example 10,000 INR = 1,000,000 paise
        # fee = 2% of 10000 = 200 INR (20,000 paise)
        # gst = 18% of 200 = 36 INR (3,600 paise)
        # net = 10000 - 200 - 36 = 9764 INR (976,400 paise)
        net, fee, gst = calc_expected_fee_net(1000000)
        self.assertEqual(fee, 20000)
        self.assertEqual(gst, 3600)
        self.assertEqual(net, 976400)


# ---------------------------------------------------------------------------
# 2. Engine Reconciliation & Discrepancy Detection Tests
# ---------------------------------------------------------------------------
class TestReconciliationEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = ReconciliationEngine()
        cls.result = cls.engine.reconcile(str(PLATFORM_CSV), str(BANK_CSV))
        cls.kpis = cls.result["kpis"]
        cls.groups = cls.result["groups"]
        cls.gt_df = pd.read_csv(GROUND_TRUTH_CSV)

    def test_row_counts_and_group_volume(self):
        self.assertEqual(self.result["platform_rows_count"], 500)
        self.assertEqual(self.result["bank_rows_count"], 495)
        # Ground truth has 504 groups
        self.assertEqual(self.kpis["total_groups"], 504)
        self.assertEqual(self.kpis["clean_matches_count"], 392)
        self.assertEqual(self.kpis["anomaly_groups_count"], 112)

    def test_exact_financial_kpi_totals(self):
        # Check against numbers established in dataset_decisions.md
        self.assertEqual(self.kpis["platform_effective_inr"], 3580093.74)
        self.assertEqual(self.kpis["bank_effective_inr"], 3815734.68)
        self.assertEqual(self.kpis["final_gap_inr"], -235640.94)
        self.assertEqual(self.kpis["cutoff_gap_inr"], -85233.39)
        self.assertEqual(self.kpis["timing_transit_gap_inr"], 150407.55)

    def test_the_4_gap_types_categorization(self):
        gap_bd = self.kpis["gap_types_breakdown"]
        
        # Verify all 4 primary gap types + unmatched are present
        self.assertIn(GAP_TYPE_TIMING, gap_bd)
        self.assertIn(GAP_TYPE_AMOUNT, gap_bd)
        self.assertIn(GAP_TYPE_STATUS, gap_bd)
        self.assertIn(GAP_TYPE_OPERATIONAL, gap_bd)
        self.assertIn(GAP_TYPE_UNMATCHED_PLATFORM, gap_bd)
        self.assertIn(GAP_TYPE_UNMATCHED_BANK, gap_bd)
        self.assertIn(GAP_TYPE_CLEAN, gap_bd)

        # 1. Timing Gaps: 32 groups (20 month-end cutoff + 8 weekend lag + 4 prior period spillover)
        self.assertEqual(gap_bd[GAP_TYPE_TIMING]["count"], 32)
        self.assertEqual(gap_bd[GAP_TYPE_TIMING]["gap_cutoff_inr"], 96269.84)
        self.assertEqual(gap_bd[GAP_TYPE_TIMING]["gap_final_inr"], -54137.71)

        # 2. Amount Discrepancies: 20 groups (12 fee + 3 partial + 3 rounding + 2 wrong amount)
        self.assertEqual(gap_bd[GAP_TYPE_AMOUNT]["count"], 20)
        self.assertEqual(gap_bd[GAP_TYPE_AMOUNT]["gap_final_inr"], -29391.54)

        # 3. Status Conflicts: 8 groups (2 success/failed + 2 success/reversed + 2 failed/success + 2 pending/success)
        self.assertEqual(gap_bd[GAP_TYPE_STATUS]["count"], 8)
        self.assertEqual(gap_bd[GAP_TYPE_STATUS]["gap_final_inr"], -68440.27)

        # 4. Operational & Duplicates: 27 groups
        # (3 plat dup + 3 bank dup + 3 same amt + 2 batches + 2 ref processed + 2 ref no orig + 2 chargeback + 10 ref format/trunc/miss)
        self.assertEqual(gap_bd[GAP_TYPE_OPERATIONAL]["count"], 27)

        # Unmatched Platform (Missing in bank): 15 groups
        self.assertEqual(gap_bd[GAP_TYPE_UNMATCHED_PLATFORM]["count"], 15)
        self.assertEqual(gap_bd[GAP_TYPE_UNMATCHED_PLATFORM]["gap_final_inr"], 15305.59)

        # Unmatched Bank (Missing in platform): 10 groups
        self.assertEqual(gap_bd[GAP_TYPE_UNMATCHED_BANK]["count"], 10)
        self.assertEqual(gap_bd[GAP_TYPE_UNMATCHED_BANK]["gap_final_inr"], -103586.87)

    def test_all_24_anomaly_scenarios_detected(self):
        """Verify that every single one of the 24 injected anomaly types is detected."""
        type_bd = self.kpis["anomaly_types_breakdown"]
        
        expected_scenarios = {
            "CLEAN_MATCH": 392,
            "TIMING_MONTH_END_CUTOFF": 20,
            "TIMING_WEEKEND_LAG": 8,
            "TIMING_PRIOR_PERIOD_SPILLOVER": 4,
            "AMOUNT_FEE_DEDUCTION": 12,
            "AMOUNT_PARTIAL_SETTLEMENT": 3,
            "AMOUNT_ROUNDING": 3,
            "AMOUNT_WRONG_AMOUNT": 2,
            "DUPLICATE_PLATFORM": 3,
            "DUPLICATE_BANK": 3,
            "SAME_AMOUNT_SAME_DAY": 3,
            "STATUS_PLATFORM_SUCCESS_BANK_FAILED": 2,
            "STATUS_PLATFORM_SUCCESS_BANK_REVERSED": 2,
            "STATUS_PLATFORM_FAILED_BANK_SUCCESS": 2,
            "STATUS_PLATFORM_PENDING_BANK_SUCCESS": 2,
            "REFUND_PROCESSED": 2,
            "REFUND_NO_ORIGINAL": 2,
            "CHARGEBACK_NOT_IN_PLATFORM": 2,
            "BATCH_SETTLEMENT": 2,
            "REF_MISSING": 4,
            "REF_TRUNCATED": 3,
            "REF_FORMAT_MISMATCH": 3,
            "MISSING_IN_BANK": 15,
            "MISSING_IN_PLATFORM": 10,
        }

        for scenario, expected_count in expected_scenarios.items():
            self.assertIn(scenario, type_bd, f"Scenario '{scenario}' missing from reconciliation breakdown.")
            self.assertEqual(
                type_bd[scenario]["count"],
                expected_count,
                f"Mismatch for '{scenario}': expected {expected_count}, got {type_bd[scenario]['count']}"
            )

    def test_perfect_accuracy_against_ground_truth(self):
        """Assert 100% precision, recall, and category accuracy against ground_truth.csv."""
        eval_res = self.engine.evaluate_against_ground_truth(str(GROUND_TRUTH_CSV), self.result)
        
        self.assertEqual(eval_res["total_records_evaluated"], 995)
        self.assertEqual(eval_res["category_accuracy"], 1.0, "Category accuracy is not 100%")
        self.assertEqual(eval_res["type_accuracy"], 1.0, "Anomaly type accuracy is not 100%")
        self.assertEqual(eval_res["counterparts_accuracy"], 1.0, "Counterparts agreement is not 100%")
        self.assertTrue(eval_res["is_perfect_match"])

        # Check precision and recall for all types
        for atype, stats in eval_res["per_type_metrics"].items():
            self.assertEqual(stats["precision"], 1.0, f"Precision not 1.0 for {atype}")
            self.assertEqual(stats["recall"], 1.0, f"Recall not 1.0 for {atype}")

    def test_csv_export_format(self):
        csv_str = self.engine.export_to_csv(self.result)
        self.assertTrue(csv_str.startswith("group_id,gap_type,gap_type_label"))
        lines = csv_str.strip().split("\n")
        # 1 header + 504 rows = 505 lines
        self.assertEqual(len(lines), 505)


# ---------------------------------------------------------------------------
# 3. Web Server & REST API In-Memory Request Tests (Zero Socket Dependencies)
# ---------------------------------------------------------------------------
class MockSocket:
    def __init__(self, request_bytes):
        self.rfile = io.BytesIO(request_bytes)
        self.wfile = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        if "b" in mode:
            if "r" in mode:
                return self.rfile
            return self.wfile
        raise NotImplementedError

    def sendall(self, data):
        self.wfile.write(data)

def invoke_handler(method, path, headers=None, body=b""):
    headers = headers or {}
    req_lines = [f"{method} {path} HTTP/1.1"]
    for k, v in headers.items():
        req_lines.append(f"{k}: {v}")
    if body and "Content-Length" not in headers:
        req_lines.append(f"Content-Length: {len(body)}")
    req_bytes = ("\r\n".join(req_lines) + "\r\n\r\n").encode("utf-8") + body

    sock = MockSocket(req_bytes)
    # Instantiate handler with mock socket
    ReconciliationHandler(sock, ("127.0.0.1", 12345), None)
    
    resp_bytes = sock.wfile.getvalue()
    parts = resp_bytes.split(b"\r\n\r\n", 1)
    header_part = parts[0].decode("utf-8", errors="replace")
    body_part = parts[1] if len(parts) > 1 else b""
    status_line = header_part.split("\r\n")[0]
    status_code = int(status_line.split(" ")[1])
    return status_code, header_part, body_part


class TestWebPlatformAPI(unittest.TestCase):
    def test_health_endpoint(self):
        status, headers, body = invoke_handler("GET", "/health")
        self.assertEqual(status, 200)
        data = json.loads(body.decode())
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "payments-reconciliation-platform")

    def test_static_index_serving(self):
        status, headers, body = invoke_handler("GET", "/")
        self.assertEqual(status, 200)
        html = body.decode()
        self.assertIn("FinRecon", html)
        self.assertIn("Reconciliation Gap Taxonomy", html)

    def test_reconcile_sample_endpoint(self):
        status, headers, body = invoke_handler("POST", "/api/reconcile-sample")
        self.assertEqual(status, 200)
        data = json.loads(body.decode())
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["kpis"]["total_groups"], 504)
        self.assertEqual(data["data"]["kpis"]["final_gap_inr"], -235640.94)

    def test_benchmark_endpoint(self):
        status, headers, body = invoke_handler("POST", "/api/benchmark")
        self.assertEqual(status, 200)
        data = json.loads(body.decode())
        self.assertTrue(data["success"])
        self.assertEqual(data["benchmark"]["type_accuracy"], 1.0)
        self.assertEqual(data["benchmark"]["is_perfect_match"], True)

    def test_export_endpoint(self):
        status, headers, body = invoke_handler("GET", "/api/export")
        self.assertEqual(status, 200)
        self.assertIn("Content-Type: text/csv", headers)
        self.assertTrue(body.startswith(b"group_id,gap_type"))

    def test_reconcile_json_upload(self):
        with open(PLATFORM_CSV, "r", encoding="utf-8") as f:
            p_text = f.read()
        with open(BANK_CSV, "r", encoding="utf-8") as f:
            b_text = f.read()

        payload = json.dumps({
            "platform_csv": p_text,
            "bank_csv": b_text,
            "platform_filename": "uploaded_p.csv",
            "bank_filename": "uploaded_b.csv"
        }).encode("utf-8")

        status, headers, body = invoke_handler(
            "POST",
            "/api/reconcile",
            headers={"Content-Type": "application/json"},
            body=payload
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode())
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["kpis"]["total_groups"], 504)

    def test_reconcile_multipart_upload(self):
        with open(PLATFORM_CSV, "r", encoding="utf-8") as f:
            p_text = f.read()
        with open(BANK_CSV, "r", encoding="utf-8") as f:
            b_text = f.read()

        boundary = "---------------------------974767299852498929531610575"
        body_parts = [
            f"--{boundary}",
            'Content-Disposition: form-data; name="platform_file"; filename="plat.csv"',
            "Content-Type: text/csv",
            "",
            p_text,
            f"--{boundary}",
            'Content-Disposition: form-data; name="bank_file"; filename="bnk.csv"',
            "Content-Type: text/csv",
            "",
            b_text,
            f"--{boundary}--",
            ""
        ]
        body_bytes = "\r\n".join(body_parts).encode("utf-8")

        status, headers, body = invoke_handler(
            "POST",
            "/api/reconcile",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            body=body_bytes
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode())
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["kpis"]["total_groups"], 504)

    def test_missing_files_error_handling(self):
        payload = json.dumps({"platform_csv": "header\n"}).encode("utf-8")
        status, headers, body = invoke_handler(
            "POST",
            "/api/reconcile",
            headers={"Content-Type": "application/json"},
            body=payload
        )
        self.assertEqual(status, 400)
        data = json.loads(body.decode())
        self.assertFalse(data["success"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
