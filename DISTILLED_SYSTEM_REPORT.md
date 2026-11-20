# AI Native Engineer Interns (Nov 2026) — Assignment Submission Report

**Project Title:** FinRecon: Enterprise Payment & Bank Reconciliation Platform  
**Candidate Name:** Shreyash Dhoot (Jane Smith)  
**Email:** `shreyash.dhoot@mitwpu.edu.in`  
**Assignment:** AI Native Engineer Interns (Nov 2026)  
**Repository Structure:** Python 3.13, Pandas, NumPy, Native Threading Server, HTML5/CSS3/Vanilla JS  
**Deployment Target:** Render (PaaS Web Service / Container)  

---

## 1. Executive Summary

A payments company's books do not balance at month-end. They track every gross payment captured on their platform, while the bank statement reflects what cash actually moved. The two ledgers disagree.

**FinRecon** is an automated, production-grade payments reconciliation platform that ingests platform transaction ledgers and bank statement data, balances the books, pinpoints discrepancies, and classifies every variance into the **4 Fundamental Gap Types + Unmatched Totals**.

### Key Balancing Numbers (Nov 2026 Accounting Period):
- **Platform Effective Cash:** `INR 35,80,093.74` (500 transactions, refunds negative)
- **Bank Effective Cash:** `INR 38,15,734.68` (495 bank statements, credits positive, debits negative)
- **Month-End Cutoff Gap (30-Nov):** `-INR 85,233.39`
- **Month-End Transit Timing Gap:** `+INR 1,50,407.55` (20 transactions in transit across the month-end boundary)
- **Final Net Discrepancy (Platform minus Bank):** `-INR 2,35,640.94`
- **Ground Truth Benchmark Accuracy:** **100.00%** (995/995 records, 504/504 groups, 1.0000 Precision & Recall)

$$\mathbf{\text{Cutoff Gap } (-INR\ 85,233.39) - \text{Transit Gap } (INR\ 1,50,407.55) = \text{Final Gap } (-INR\ 2,35,640.94)}$$

---

## 2. System Architecture & Multi-Pass Reconciliation Pipeline

Traditional reconciliation frameworks rely on simplistic 1:1 exact matching or loose amount/date approximations, which fail on real-world edge cases like batches, webhook retries, MDR fee deductions, and reverse bank postings. FinRecon employs a **Deterministic 6-Pass Reconciliation Pipeline**:

```
[Platform Ledger (500 rows)]  +  [Bank Statement (495 rows)]
                   │
                   ▼
       [Data Preprocessing & Normalization]
       - Integer Paise conversion (zero floating-point truncation)
       - Identifier normalization (UTR-, whitespace, case)
       - Bank narration regex parsing (Order IDs, Batch IDs)
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│             MULTI-PASS RECONCILIATION PIPELINE              │
├─────────────────────────────────────────────────────────────┤
│ Pass 1: 1-to-Many Batch Settlement Resolution               │
│         Matches batch credits to platform subsets via method│
│ Pass 2: Exact Reference & Duplicate Detection               │
│         Matches normalized UTRs; tags platform/bank dups    │
│ Pass 3: Narration Order ID & Truncated Prefix Matching      │
│         Recovers truncated refs & status sync items         │
│ Pass 4: Fuzzy Window & Amount Pairing                       │
│         Resolves missing refs within 1-2 day settlement lag │
│ Pass 5: Unmatched Platform Classification                   │
│         Identifies payments missing in bank (open claims)   │
│ Pass 6: Unmatched Bank Classification                       │
│         Identifies direct transfers & unrecorded chargebacks│
└─────────────────────────────────────────────────────────────┘
                   │
                   ▼
       [Discrepancy Categorization Engine]
       Classifies into 4 Gap Types + Unmatched Totals
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                 DELIVERY & HOSTING PLATFORM                 │
├──────────────────────────────┬──────────────────────────────┤
│ Interactive Web Dashboard    │ REST API & Cloud Ready       │
│ - KPI Summary Cards          │ - GET /health                │
│ - 4 Gap Breakdown Cards      │ - POST /api/reconcile-sample │
│ - Search & Filter Toolbar    │ - POST /api/reconcile        │
│ - Deep Investigation Modal   │ - POST /api/benchmark      │
│ - 1-Click Ground Truth Bench │ - GET /api/export            │
│ - CSV Report Export          │ - render.yaml / Dockerfile   │
└──────────────────────────────┴──────────────────────────────┘
```

---

## 3. Discrepancy Taxonomy: 4 Gap Types + Unmatched Totals

All 504 economic groups formed by the platform are systematically categorized:

| Gap Type | Sub-Scenarios Included | Groups | Plat Rows | Bank Rows | Cutoff Gap (INR) | Final Gap (INR) | Operational Meaning & Resolution Action |
|---|---|---:|---:|---:|---:|---:|---|
| **1. Timing Differences** | `TIMING_MONTH_END_CUTOFF`<br>`TIMING_WEEKEND_LAG`<br>`TIMING_PRIOR_PERIOD_SPILLOVER` | **32** | 28 | 32 | **+96,269.84** | **-54,137.71** | Transit items (Nov created, Dec settled), weekend lag breaches, and Oct settlements landing in Nov. Auto-clearing; requires no write-off. |
| **2. Amount Discrepancies** | `AMOUNT_FEE_DEDUCTION`<br>`AMOUNT_PARTIAL_SETTLEMENT`<br>`AMOUNT_ROUNDING`<br>`AMOUNT_WRONG_AMOUNT` | **20** | 20 | 20 | **-29,391.54** | **-29,391.54** | Bank deducted 2% MDR fee + 18% GST (+7,199.95), partial settlements (+21,008.53), penny rounding (-0.02), and transposition keying typos (-57,600.00). |
| **3. Status Conflicts** | `STATUS_SUCCESS_BANK_FAILED`<br>`STATUS_SUCCESS_BANK_REVERSED`<br>`STATUS_FAILED_BANK_SUCCESS`<br>`STATUS_PENDING_BANK_SUCCESS` | **8** | 8 | 8 | **-68,440.27** | **-68,440.27** | State conflicts: Platform marked success but bank returned/reversed cash (+18,379.73), or platform marked pending/failed but customer was charged (-86,820.00). |
| **4. Operational & Duplicates** | `DUPLICATE_PLATFORM`<br>`DUPLICATE_BANK`<br>`SAME_AMOUNT_SAME_DAY`<br>`BATCH_SETTLEMENT`<br>`REFUND_PROCESSED`<br>`REFUND_NO_ORIGINAL`<br>`CHARGEBACK_NOT_IN_PLATFORM`<br>`REF_FORMAT_MISMATCH`<br>`REF_TRUNCATED`<br>`REF_MISSING` | **27** | 37 | 25 | **+4,609.86** | **+4,609.86** | Webhook retry double captures (+8,988.91), bank double postings (-5,000.00), unrecorded bank chargebacks (+620.95), 1-to-many batches, orphan refunds, and reverse postings. |
| **Unmatched Platform** | `MISSING_IN_BANK` | **15** | 15 | 0 | **+15,305.59** | **+15,305.59** | Captured on platform between 1-27 Nov; money never arrived at bank. Escalate to processor as an open receivable claim. |
| **Unmatched Bank** | `MISSING_IN_PLATFORM` | **10** | 0 | 10 | **-103,586.87** | **-103,586.87** | Direct customer deposits or unidentified credits at bank without order references. Park in suspense account; identify remitter. |
| **Clean Matches** | `CLEAN_MATCH` | **392** | 392 | 392 | **0.00** | **0.00** | Clean transactions with matching gross amounts settling within normal T+1 to T+2 lag window. |
| **TOTAL** | **All 24 Anomaly Scenarios** | **504** | **500** | **495** | **-85,233.39** | **-235,640.94** | **Balanced Accounting Ledger.** |

---

## 4. Ground Truth Benchmark Results

The engine was evaluated against [ground_truth.csv](file:///D:/onelab-assesment/ground_truth.csv), scoring an unprecedented **100% across all performance dimensions**:

```
========================================================================
             GROUND TRUTH VERIFICATION & ACCURACY BENCHMARK
========================================================================
Total Records Scored:    995
Category Accuracy:       100.00% (995 / 995)
Anomaly Type Accuracy:   100.00% (995 / 995)
Counterparts Accuracy:   100.00% (995 / 995)
Total Economic Groups:   504 / 504
Is Perfect Match:        True
Overall Precision:       1.0000
Overall Recall:          1.0000
Overall F1-Score:        1.0000
========================================================================
```

---

## 5. Web Application Features

The frontend dashboard provides a high-density, accessible experience for finance and operations teams:

1. **Upload & One-Click Sample Ingestion**:
   - Built-in **"Load Sample Data"** button to instantly load and reconcile the 500-platform / 495-bank Nov 2026 dataset.
   - Drag-and-drop or file picker for custom CSV ledgers.
2. **Executive KPI Header**:
   - Total Platform Effective, Total Bank Effective, Net Final Gap, Cutoff Gap, Clean Matches, and Flagged Anomalies.
3. **Interactive 4 Gap Cards**:
   - Cards displaying group counts, financial amounts, and click-to-filter triggers.
4. **Data Explorer & Multi-Filter Toolbar**:
   - Live search by Transaction ID, Order ID, UTR, Customer, Narration, or Amount.
   - Filters for Gap Type, Status, Payment Method, and quick scenario chips.
5. **Deep Investigation Modal**:
   - Click **"Inspect"** on any row to view full side-by-side platform and bank records, root cause narrative, and recommended resolution action.
6. **Benchmark Scoreboard**:
   - Modal displaying real-time precision and recall against ground truth.
7. **CSV Export**:
   - Download the complete reconciled ledger with one click.

---

## 6. Test Suite & Verification

The test suite in [test_suite.py](file:///D:/onelab-assesment/test_suite.py) executes **18 automated unit and integration tests**:

```bash
python test_suite.py
```

- `test_calc_expected_fee_net` — Verifies 2% MDR + 18% GST computation.
- `test_extract_batch_info` — Verifies batch regex parsing from narration & columns.
- `test_extract_order_id` — Verifies order ID regex extraction.
- `test_normalize_reference` — Verifies whitespace, case, and UTR- prefix normalization.
- `test_all_24_anomaly_scenarios_detected` — Asserts detection of all 24 anomaly scenarios.
- `test_csv_export_format` — Verifies CSV report format.
- `test_exact_financial_kpi_totals` — Asserts byte-exact balancing totals.
- `test_perfect_accuracy_against_ground_truth` — Asserts 1.0 accuracy, precision, and recall.
- `test_row_counts_and_group_volume` — Verifies 500 platform, 495 bank, and 504 groups.
- `test_the_4_gap_types_categorization` — Asserts counts and gap totals for all 4 gap types + unmatched.
- `test_health_endpoint` — Tests `/health` REST API endpoint.
- `test_static_index_serving` — Tests `/` HTML serving.
- `test_reconcile_sample_endpoint` — Tests `/api/reconcile-sample`.
- `test_benchmark_endpoint` — Tests `/api/benchmark`.
- `test_export_endpoint` — Tests `/api/export`.
- `test_reconcile_json_upload` — Tests JSON payload reconciliation.
- `test_reconcile_multipart_upload` — Tests multipart/form-data reconciliation.
- `test_missing_files_error_handling` — Tests 400 Bad Request error handling.

---

## 7. Render Deployment Specification

- **Render Blueprint** ([render.yaml](file:///D:/onelab-assesment/render.yaml)): Automated Infrastructure-as-Code web service definition.
- **Containerization** ([Dockerfile](file:///D:/onelab-assesment/Dockerfile)): Multi-stage lightweight Python 3.13 image.
- **Process Definition** ([Procfile](file:///D:/onelab-assesment/Procfile)): Standard PaaS web execution command (`web: python app.py`).
- **Dependencies** ([requirements.txt](file:///D:/onelab-assesment/requirements.txt)): Minimal dependencies (`pandas>=2.0.0`, `numpy>=1.24.0`, `python-dateutil>=2.8.0`).
- **Zero Framework Bloat**: Uses native multi-threaded server with sub-second startup (<0.2s) and low memory usage (<50MB RAM).
