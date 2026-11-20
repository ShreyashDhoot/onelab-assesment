# AI Native Engineer Interns (Nov 2026) — Raw Prompt & Engineering Log

**Assignment:** AI Native Engineer Interns (Nov 2026)  
**Project:** FinRecon Payments Reconciliation Platform  
**Candidate Name:** Shreyash Dhoot (Jane Smith)  
**Email:** `shreyash.dhoot@mitwpu.edu.in`  

---

## 1. Initial Raw User Prompt

```text
/goal @dataset_decisions.md includes decisions we took for generating the dataset for the task. we have 2 csv @bank_transactions.csv @platform_transactions.csv  and a third csv @ground_truth.csv . we have to design a system to reconsile these two csv files transaction data and host it using render as a platform the thrid csv is to test if our framework works or not properly. The platform will have option to upload 2 csv files and and a load sample data button built in Reconcile by ID/amount/date window, flag discrepancies, and categorize them into the 4 gap types + unmatched totals. UI : show summary KPI cards total platfom , total bank , discrepencies and filters for being able to see anamolies . Write a test suite also to check our platform implementations and also tests for if we are catching all the discrepenceies properly
```

---

## 2. Problem Deconstruction & Requirements Mapping

### Prompt Objectives:
1. Reconcile `platform_transactions.csv` (500 rows) and `bank_transactions.csv` (495 rows) based on specifications in `dataset_decisions.md`.
2. Benchmark and verify accuracy against `ground_truth.csv` (995 records, 504 economic groups).
3. Build an interactive web platform with:
   - Upload option for 2 CSV files
   - Built-in **"Load Sample Data"** button
   - Multi-stage reconciliation: by ID (UTR, Order ID, truncated refs), amount, settlement date window
   - Discrepancy flagging and categorization into the **4 Gap Types + Unmatched Totals**
   - Executive KPI cards: Total Platform Effective, Total Bank Effective, Net Discrepancies, Cutoff Gap
   - Filters & Search toolbar to inspect and drill down into anomalies
4. Build an automated test suite verifying platform implementations, discrepancy detection, and 100% precision/recall against ground truth.
5. Deploy and host on **Render** as a web service.

---

## 3. Engineering Log & Technical Iterations

### Phase 1: Dataset & Ground Truth Analysis
- Examined `dataset_decisions.md` and `generate_recon_dataset.py`.
- Identified the 24 anomaly scenarios across 9 categories (`MATCHED`, `TIMING`, `AMOUNT`, `DUPLICATE`, `STATUS`, `REFUND_REVERSAL`, `BATCH`, `REFERENCE`, `MISSING`).
- Established the financial accounting identity:
  $$\text{Cut-off Gap } (-₹85,233.39) - \text{Transit Gap } (₹1,50,407.55) = \text{Final Gap } (-₹2,35,640.94)$$
- Verified sign conventions: Platform stores refunds as negative amounts; bank stores them as positive amounts with `credit_debit = DEBIT`.

### Phase 2: Core Engine Development (`reconciliation_engine.py`)
- Built multi-pass deterministic matching pipeline:
  - **Pass 1 (Batches)**: Grouping 1-to-many transactions by method, date window, and sum matching batch credit.
  - **Pass 2 (Exact Ref)**: Normalizing UTR formats (handling `"UTR- 1234 5678 9012"`, whitespace, lowercase) and matching 1:1, detecting webhook retries and duplicate bank credits.
  - **Pass 3 (Narration Orders)**: Extracting `ORD-2026-xxxxxx` from bank narration to resolve truncated refs and status mismatches.
  - **Pass 4 (Fuzzy Window & Amount)**: Pairing unreferenced records by amount and 1-2 day lag window.
  - **Pass 5 & 6 (Unmatched Totals)**: Classifying `MISSING_IN_BANK`, `MISSING_IN_PLATFORM`, prior period spillovers, and disputes.
- *Iteration 1 Bug Solved*: Floating-point truncation where `round(val, 2) * 100` yielded `...35.999999998` and cast to integer lost 1 paisa on batch transactions. Solved using `np.round(df['amount_inr'] * 100).astype(int)`.
- *Result*: Achieved **100.00% accuracy, precision, and recall** across all 995 records and 504 groups.

### Phase 3: Web Server & REST API (`app.py`)
- Implemented lightweight `ThreadingHTTPServer` with native Python standard library:
  - Endpoints: `GET /`, `GET /health`, `POST /api/reconcile`, `POST /api/reconcile-sample`, `POST /api/benchmark`, `GET /api/export`.
  - Added dynamic port detection via `os.environ.get("PORT", 8000)` for Render compatibility.

### Phase 4: Frontend Dashboard Implementation (`static/`)
- Developed single-page fintech dashboard in HTML5, CSS3, and modern Vanilla JS:
  - Executive KPI summary cards (Total Platform, Total Bank, Final Gap, Cutoff Gap, Clean Matches, Flagged Anomalies).
  - 4 Gap Types + Unmatched cards with group counts and financial metrics.
  - Interactive filter toolbar (Gap type select, status select, payment method select, live search input, quick scenario chips).
  - Reconciled transaction grid with pagination.
  - Investigation modal displaying side-by-side platform and bank records, root cause analysis, and operational resolution actions.
  - Benchmark scoreboard modal displaying accuracy and confusion matrix.

### Phase 5: Production Debugging & Hardening
- *Iteration 2 Bug Solved (Windows Client URL)*: Browser showed `ERR_ADDRESS_INVALID` when users navigated to `http://0.0.0.0:8000`. Updated server to print `http://localhost:8000` and `http://127.0.0.1:8000`, implemented dual-stack IPv4/IPv6 socket binding, and added automatic browser launch.
- *Iteration 3 Bug Solved (JSON NaN Serialization)*: Pandas empty cells produced `np.nan`, which Python's `json.dumps()` emitted as `NaN`, causing browser `JSON.parse()` to throw `SyntaxError: Unexpected token 'N'`. Built recursive `sanitize_for_json()` serializer converting all `NaN`/`Inf` to compliant JSON `null` and formatting timestamps.
- *Iteration 4 Bug Solved (Multipart Form Parsing)*: Built fail-safe `get_part_text()` helper in `app.py` and upgraded `app.js` to read files using `FileReader.readAsText()` and send clean JSON payloads, eliminating multipart encoding errors.

### Phase 6: Automated Test Suite (`test_suite.py`)
- Built 18 automated tests covering:
  - Helpers (reference normalization, order regex, batch regex, MDR fee calculation).
  - Discrepancy detection (asserting all 24 anomaly scenarios).
  - Financial KPI calculations (exact balancing figures).
  - 100% precision and recall benchmark against `ground_truth.csv`.
  - REST API endpoint integration (`/health`, `/api/reconcile-sample`, `/api/reconcile`, `/api/benchmark`, `/api/export`).
- All 18 tests pass in ~1.0 second.

---

## 4. Verification Checksum & Test Output

```
test_calc_expected_fee_net (__main__.TestHelperFunctions.test_calc_expected_fee_net) ... ok
test_extract_batch_info (__main__.TestHelperFunctions.test_extract_batch_info) ... ok
test_extract_order_id (__main__.TestHelperFunctions.test_extract_order_id) ... ok
test_normalize_reference (__main__.TestHelperFunctions.test_normalize_reference) ... ok
test_all_24_anomaly_scenarios_detected (__main__.TestReconciliationEngine.test_all_24_anomaly_scenarios_detected) ... ok
test_csv_export_format (__main__.TestReconciliationEngine.test_csv_export_format) ... ok
test_exact_financial_kpi_totals (__main__.TestReconciliationEngine.test_exact_financial_kpi_totals) ... ok
test_perfect_accuracy_against_ground_truth (__main__.TestReconciliationEngine.test_perfect_accuracy_against_ground_truth) ... ok
test_row_counts_and_group_volume (__main__.TestReconciliationEngine.test_row_counts_and_group_volume) ... ok
test_the_4_gap_types_categorization (__main__.TestReconciliationEngine.test_the_4_gap_types_categorization) ... ok
test_benchmark_endpoint (__main__.TestWebPlatformAPI.test_benchmark_endpoint) ... ok
test_export_endpoint (__main__.TestWebPlatformAPI.test_export_endpoint) ... ok
test_health_endpoint (__main__.TestWebPlatformAPI.test_health_endpoint) ... ok
test_missing_files_error_handling (__main__.TestWebPlatformAPI.test_missing_files_error_handling) ... ok
test_reconcile_json_upload (__main__.TestWebPlatformAPI.test_reconcile_json_upload) ... ok
test_reconcile_multipart_upload (__main__.TestWebPlatformAPI.test_reconcile_multipart_upload) ... ok
test_reconcile_sample_endpoint (__main__.TestWebPlatformAPI.test_reconcile_sample_endpoint) ... ok
test_static_index_serving (__main__.TestWebPlatformAPI.test_static_index_serving) ... ok

----------------------------------------------------------------------
Ran 18 tests in 1.120s

OK
```
