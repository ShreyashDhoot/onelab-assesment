# FinRecon: Enterprise Payment & Bank Reconciliation Platform

**FinRecon** is an automated reconciliation platform designed to balance payments company transaction ledgers against bank settlement statements. It systematically resolves month-end discrepancies, identifies root causes, and categorizes variances into the **4 Fundamental Gap Types + Unmatched Totals**.

The platform includes:
- **Core Reconciliation Engine** (`reconciliation_engine.py`): Multi-pass identifier matching, 1-to-many batch settlement grouping, duplicate detection, and anomaly classification with **100% precision and recall** against ground truth.
- **Production Web Dashboard & REST API** (`app.py`): Interactive fintech dashboard with KPI cards, 4 gap breakdown cards, live anomaly search & filtering, CSV upload, one-click **"Load Sample Data"**, and ground-truth benchmark verification.
- **Comprehensive Test Suite** (`test_suite.py`): 18 automated unit and integration tests verifying all 24 anomaly types, financial KPIs, and REST endpoints.
- **Render Deployment Ready** (`render.yaml`, `Dockerfile`, `Procfile`): Zero-configuration deployment to [Render](https://render.com).

---

## 1. Executive Summary & Financial KPIs

When reconciling the November 2026 dataset (`500` platform rows, `495` bank rows):

| Metric | Amount (INR) | Records / Groups | Meaning & Explanation |
|---|---|---|---|
| **Platform Total Effective** | **₹35,80,093.74** | 500 rows | Total cash earned from `SUCCESS` platform rows (refunds negative). |
| **Bank Total Effective** | **₹38,15,734.68** | 495 rows | Total cash settled at the bank (`CREDIT` minus `DEBIT`, `SUCCESS` only). |
| **Final Net Discrepancy (P - B)** | **-₹2,35,640.94** | 504 groups | True residual financial variance requiring ledger adjustments. |
| **Accounting Cut-off Gap (30-Nov)** | **-₹85,233.39** | - | Month-end ledger difference before transit items clear in December. |
| **Month-End Transit Timing Difference** | **₹1,50,407.55** | 20 groups | Platform transactions booked on 29-30 Nov that settle in bank on 1-2 Dec. |
| **Clean Matches (1:1)** | **₹26,14,137.43** | 392 groups | Clean transactions that settled 1:1 within normal settlement lag (T+1 to T+2). |
| **Discrepancies Flagged** | **₹9,65,956.31** | 112 groups | Anomalies requiring operational investigation across 4 gap categories. |

> **Accounting Identity**:
> `Cut-off Gap (-₹85,233.39) - Month-End Transit Gap (₹1,50,407.55) = Final Gap (-₹2,35,640.94)`.

---

## 2. The 4 Gap Types + Unmatched Totals Taxonomy

Discrepancies are categorized into 4 core operational gap types plus unmatched orphan totals:

### 1. Timing Differences (32 groups)
* **Month-End Cut-Off (`TIMING_MONTH_END_CUTOFF`)** (20 groups): Platform captures payment on 29-30 Nov; bank credit lands on 1-2 Dec. Net final gap is ₹0.00 once transit clears.
* **Weekend SLA Lag (`TIMING_WEEKEND_LAG`)** (8 groups): Created on Fri/Sat, bank settlement settled after 3 days due to non-processing days. Flagged as SLA breach.
* **Prior-Period Spillover (`TIMING_PRIOR_PERIOD_SPILLOVER`)** (4 groups): Bank credits landing on 1-2 Nov belonging to October orders (`ORD-2026-09xxxx`). Total bank excess: `-₹54,137.71`.

### 2. Amount Discrepancies (20 groups)
* **Gateway MDR Fee & GST (`AMOUNT_FEE_DEDUCTION`)** (12 groups): Bank credited net cash after deducting 2% MDR fee + 18% GST on fee. Total variance: `+₹7,199.95`.
* **Partial Settlement (`AMOUNT_PARTIAL_SETTLEMENT`)** (3 groups): Processor paid 50-90% of order amount; remainder uncollected. Shortfall: `+₹21,008.53`.
* **Paise Rounding (`AMOUNT_ROUNDING`)** (3 groups): Fractional variances of ±1-2 paise. Net variance: `-₹0.02`.
* **Wrong Amount / Keying Error (`AMOUNT_WRONG_AMOUNT`)** (2 groups): Transposition keying errors (e.g. 18,540 vs 15,840). Net variance: `-₹57,600.00`.

### 3. Status Conflicts (8 groups)
* **Success vs Bank Failed (`STATUS_PLATFORM_SUCCESS_BANK_FAILED`)** (2 groups): Platform shows success, bank leg failed/returned. Variance: `+₹9,975.00`.
* **Success vs Bank Reversed (`STATUS_PLATFORM_SUCCESS_BANK_REVERSED`)** (2 groups): Platform shows success, bank credit reversed. Variance: `+₹8,404.73`.
* **Failed vs Bank Success (`STATUS_PLATFORM_FAILED_BANK_SUCCESS`)** (2 groups): Platform marked failed, bank credited cash. Variance: `-₹45,481.00`.
* **Pending vs Bank Success (`STATUS_PLATFORM_PENDING_BANK_SUCCESS`)** (2 groups): Missed callback; bank settled. Variance: `-₹41,339.00`.

### 4. Operational & Structural Anomalies (27 groups)
* **Webhook Duplicates (`DUPLICATE_PLATFORM`)** (3 groups, 6 plat rows, 3 bank rows): Duplicate webhook retries within seconds. Platform overstated by `+₹8,988.91`.
* **Bank Duplicates (`DUPLICATE_BANK`)** (3 groups, 3 plat rows, 6 bank rows): Ledger credited twice by bank. Bank surplus: `-₹5,000.00`.
* **Same Amount Same Day (`SAME_AMOUNT_SAME_DAY`)** (3 groups, 6 plat rows, 6 bank rows): Two identical-amount UPI orders posted in reverse bank order; resolved via UTR matching.
* **Batch Lump-Sum Settlements (`BATCH_SETTLEMENT`)** (2 groups: sizes 3 and 5): Multiple platform transactions settled as single bank lump-sum with `batch_id`.
* **Processed Refunds (`REFUND_PROCESSED`)** (2 groups): Legitimate refunds paired by normalising negative platform amount to positive bank DEBIT.
* **Orphan Refunds (`REFUND_NO_ORIGINAL`)** (2 groups): Refund pointing to ghost transaction IDs (`PTX0009001`/`PTX0009002`).
* **Unrecorded Chargebacks (`CHARGEBACK_NOT_IN_PLATFORM`)** (2 groups): Bank debit with narration `CHARGEBACK/DISPUTE/<utr>` not recorded in platform. Impact: `+₹620.95`.
* **Identifier Formatting & Truncation (`REF_FORMAT_MISMATCH`, `REF_TRUNCATED`, `REF_MISSING`)** (10 groups): UTR whitespace, prefix `UTR-`, truncated prefixes, or missing refs resolved via order ID in narration or fuzzy amount-window pairing.

### Unmatched Totals (25 rows)
* **Unmatched Platform / Missing in Bank (`MISSING_IN_BANK`)** (15 rows): Platform captured on 1-27 Nov, bank credit never arrived. Open claim: `+₹15,305.59`.
* **Unmatched Bank / Missing in Platform (`MISSING_IN_PLATFORM`)** (10 rows): Direct customer transfers without order IDs. Suspense payable: `-₹1,03,586.87`.

---

## 3. Ground Truth Verification Benchmark

FinRecon was scored directly against `ground_truth.csv` (the independent 995-row answer key):

```
============================================================
              GROUND TRUTH EVALUATION REPORT
============================================================
Total Records Evaluated: 995
Category Accuracy:       100.00% (995/995)
Anomaly Type Accuracy:   100.00% (995/995)
Counterparts Agreement:  100.00% (995/995)
Total Groups Reconciled: 504 / 504
Is Perfect Match:        True
============================================================
```

Every single injected anomaly scenario achieved **Precision = 1.0000** and **Recall = 1.0000**.

---

## 4. Web Platform Architecture & Features

The platform provides an enterprise dashboard served by `app.py`:

- **One-Click Sample Data**: Click **"⚡ Load Sample Data"** to instantly load and reconcile the Nov 2026 dataset.
- **Drag & Drop CSV Upload**: Upload any custom platform and bank CSVs.
- **Interactive KPI Cards**: Real-time totals, effective cash, final gap, and cutoff variance.
- **Interactive 4 Gap Types Cards**: Click any gap card to automatically filter the transaction grid.
- **Multi-Filter & Search Toolbar**: Search by Transaction ID, UTR, Order ID, Customer ID, Narration, Amount, or filter by Gap Category and Payment Method.
- **Deep Investigation Modal**: Click **"Inspect"** on any row to view full side-by-side transaction breakdown, root cause narrative, and recommended resolution action.
- **Benchmark Modal**: View live precision and recall metrics verifying accuracy against `ground_truth.csv`.
- **Export CSV**: One-click download of the complete reconciled ledger report.

---

## 5. Quick Start & Local Execution

### Prerequisites
- Python 3.10+ (tested on Python 3.13)
- `pandas>=2.0.0`, `numpy>=1.24.0`, `python-dateutil>=2.8.0`

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Web Platform
```bash
python app.py
```
Open your browser at `http://localhost:8000`.

### 3. Run the Automated Test Suite
```bash
python test_suite.py
```
Or via standard unittest:
```bash
python -m unittest test_suite.py
```

---

## 6. Hosting on Render

The repository is configured for 1-click deployment on [Render](https://render.com).

### Method A: Deploy via Render Blueprint (`render.yaml`)
1. Push this repository to GitHub or GitLab.
2. In the Render Dashboard, click **New +** → **Blueprint**.
3. Connect your repository. Render automatically reads `render.yaml` and provisions the web service.
4. Render builds and launches `python app.py` on the assigned public URL.

### Method B: Deploy as a Standard Web Service
1. In the Render Dashboard, click **New +** → **Web Service**.
2. Connect your Git repository.
3. Configure the settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
   - **Health Check Path**: `/health`
4. Click **Deploy Web Service**.

### Method C: Deploy via Dockerfile
1. Select **Docker** environment on Render.
2. Render automatically builds using the included `Dockerfile` and starts the container on `PORT 8000`.

---

## 7. REST API Documentation

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check endpoint returning `{ "status": "healthy" }`. |
| `POST` | `/api/reconcile-sample` | Reconciles built-in sample files (`platform_transactions.csv` & `bank_transactions.csv`). |
| `POST` | `/api/reconcile` | Accepts `multipart/form-data` or JSON payload with `platform_file` and `bank_file` CSVs. |
| `POST` | `/api/benchmark` | Evaluates framework reconciliation against `ground_truth.csv` and returns benchmark scores. |
| `GET` | `/api/export` | Downloads the reconciled output as `reconciliation_report.csv`. |

---

## 8. File Structure

```
.
├── app.py                     # Production HTTP server & REST API
├── reconciliation_engine.py   # Core multi-pass reconciliation engine & evaluator
├── test_suite.py              # 18 automated tests (100% pass rate)
├── static/
│   ├── index.html             # Sleek single-page dashboard UI
│   ├── styles.css             # Modern fintech styling & responsive layout
│   └── app.js                 # UI interactions, search, filter, modals, export
├── platform_transactions.csv  # 500-row platform transactions dataset
├── bank_transactions.csv      # 495-row bank statement dataset
├── ground_truth.csv           # 995-row evaluation answer key
├── dataset_decisions.md       # Dataset generation specifications
├── generate_recon_dataset.py  # Dataset generator script
├── render.yaml                # Render Infrastructure-as-Code Blueprint
├── Dockerfile                 # Containerized deployment spec
├── Procfile                   # Process configuration
├── requirements.txt           # Python package dependencies
└── README.md                  # System documentation
```
