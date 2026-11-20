#!/usr/bin/env python3
"""
generate_recon_dataset.py  --  Payments reconciliation dataset generator
=========================================================================
Scenario: a payments company's books don't balance at month end. The platform
knows every transaction it processed, the bank knows what actually arrived,
and the two disagree. This script builds a synthetic version of that mess,
plus an answer key so a reconciliation engine can be scored.

Outputs (written to --out-dir):
  platform_transactions.csv   what the platform says it processed (500 rows)
  bank_transactions.csv       what the bank statement says actually moved
  ground_truth.csv            answer key: what is really wrong and why

Assumptions
  * All amounts are INR with paise precision (2 decimals).
  * All timestamps are UTC.
  * Normal settlement window is 1-2 calendar days after the platform
    timestamp. Every "clean" row is inside this window.
  * Platform amount = gross amount the platform expects to receive. A clean
    bank credit equals it exactly; fees and short-pays are anomalies.
  * Platform stores refunds as NEGATIVE amounts; the bank stores them as a
    positive amount with credit_debit = DEBIT (a deliberate sign trap).
  * Platform activity covers 1-30 Nov 2026. The bank statement runs into
    early Dec 2026 so month-end transactions settle in the next month.
  * Month-end cut-off used for the "books don't balance" view:
    2026-11-30 23:59:59 UTC.

Usage:
  python generate_recon_dataset.py [--seed 42] [--out-dir .]
"""
import argparse
import csv
import random
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_SEED = 42
N_PLATFORM_ROWS = 500
CUTOFF = datetime(2026, 11, 30, 23, 59, 59)
DT_FMT = "%Y-%m-%d %H:%M:%S"

MDR_PCT = 2    # gateway fee, % of amount (flat, per assignment brief)
GST_PCT = 18   # GST charged on the fee

METHODS = ["UPI", "CARD", "NETBANKING", "WALLET"]
METHOD_WEIGHTS = [55, 20, 10, 15]
BATCH_SIZES = [3, 5]

# Number of anomaly "groups" per scenario. A group is one economic event and
# may span several platform and/or bank rows. Clean rows fill the remainder
# so the platform file is exactly N_PLATFORM_ROWS long.
SCENARIO_COUNTS = OrderedDict([
    ("month_end_cutoff", 20),
    ("weekend_lag", 8),
    ("fee_deduction", 12),
    ("rounding_diff", 3),
    ("partial_settlement", 3),
    ("wrong_amount", 2),
    ("missing_in_bank", 15),
    ("missing_in_platform", 10),
    ("prior_period_spillover", 4),
    ("duplicate_platform", 3),
    ("duplicate_bank", 3),
    ("same_amount_same_day", 3),
    ("status_platform_success_bank_failed", 2),
    ("status_platform_success_bank_reversed", 2),
    ("status_platform_failed_bank_success", 2),
    ("status_platform_pending_bank_success", 2),
    ("refund_processed", 2),
    ("refund_no_original", 2),
    ("chargeback", 2),
    ("batch_settlement", len(BATCH_SIZES)),
    ("ref_missing", 4),
    ("ref_truncated", 3),
    ("ref_format_mismatch", 3),
])

PLATFORM_COLS = [
    "platform_txn_id", "order_id", "customer_id", "amount_inr", "currency",
    "payment_method", "txn_type", "status", "created_at_utc", "bank_ref",
    "refund_of_txn_id",
]
BANK_COLS = [
    "bank_txn_id", "utr", "amount_inr", "credit_debit", "value_date_utc",
    "narration", "batch_id", "status",
]
TRUTH_COLS = [
    "group_id", "record_source", "record_id", "record_role",
    "anomaly_category", "anomaly_type", "is_anomaly",
    "expected_counterpart_ids", "related_record_ids", "record_amount_inr",
    "group_platform_inr", "group_bank_inr", "gap_final_inr",
    "gap_at_cutoff_inr", "settlement_lag_days", "root_cause",
    "expected_resolution",
]


# ----------------------------------------------------------------- helpers
def fmt_amount(p):
    """Paise (int) -> '1234.50' string, sign preserved."""
    sign = "-" if p < 0 else ""
    p = abs(p)
    return f"{sign}{p // 100}.{p % 100:02d}"


def inr(p):
    sign = "-" if p < 0 else ""
    p = abs(p)
    return f"{sign}INR {p // 100:,}.{p % 100:02d}"


def eff_platform(r):
    """Cash the platform believes it has earned from this row."""
    return r["amount_p"] if r["status"] == "SUCCESS" else 0


def eff_bank(r):
    """Cash that actually moved at the bank for this row."""
    if r["status"] != "SUCCESS":
        return 0
    return r["amount_p"] if r["cd"] == "CREDIT" else -r["amount_p"]


# ----------------------------------------------------------------- builder
class DatasetBuilder:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.platform = OrderedDict()
        self.bank = OrderedDict()
        self.groups = []
        self._p_seq = 0
        self._b_seq = 0
        self._orphan_seq = 0
        self.used_utrs = set()
        self.used_orders = set()

    # ---- random primitives -------------------------------------------
    def rand_amount(self, lo=None, hi=None, fractional=None):
        if lo is None:
            tier = self.rng.choices([0, 1, 2, 3], [60, 30, 9, 1])[0]
            lo, hi = [(99, 999), (1000, 9999), (10000, 49999),
                      (50000, 200000)][tier]
        rupees = self.rng.randint(lo, hi)
        if fractional is None:
            fractional = self.rng.random() < 0.3
        paise = self.rng.randint(1, 99) if fractional else 0
        return rupees * 100 + paise

    def rand_created(self, d0, d1):
        """Platform timestamp in Nov 2026, 02:30-17:30 UTC (IST daytime)."""
        day = self.rng.randint(d0, d1)
        return datetime(2026, 11, day) + timedelta(
            minutes=self.rng.randint(150, 1050), seconds=self.rng.randint(0, 59))

    def settle_dt(self, base_dt, lag_days):
        """Bank value timestamp: base date + lag, 04:00-11:59 UTC."""
        d = base_dt.date() + timedelta(days=lag_days)
        return datetime(d.year, d.month, d.day) + timedelta(
            minutes=self.rng.randint(240, 719), seconds=self.rng.randint(0, 59))

    def clean_lag(self):
        return self.rng.choices([1, 2], [60, 40])[0]

    def new_utr(self, method):
        while True:
            if method in ("UPI", "WALLET"):
                u = str(self.rng.randint(10 ** 11, 10 ** 12 - 1))  # 12 digits
            else:
                u = (self.rng.choice(["HDFCR", "ICICR", "SBINR", "AXISR"])
                     + str(self.rng.randint(10 ** 10, 10 ** 11 - 1)))  # 16 chars
            if u not in self.used_utrs:
                self.used_utrs.add(u)
                return u

    def new_order(self, prior=False):
        lo, hi = (90000, 99999) if prior else (100000, 199999)
        while True:
            n = self.rng.randint(lo, hi)
            oid = f"ORD-2026-{n:06d}"
            if oid not in self.used_orders:
                self.used_orders.add(oid)
                return oid

    def new_customer(self):
        return f"CUST{self.rng.randint(1, 150):04d}"

    # ---- row constructors --------------------------------------------
    def add_platform(self, order_id, customer_id, amount_p, method, txn_type,
                     status, created_dt, bank_ref, refund_of=None):
        self._p_seq += 1
        key = f"P{self._p_seq:05d}"
        row = dict(key=key, order_id=order_id, customer_id=customer_id,
                   amount_p=amount_p, method=method, txn_type=txn_type,
                   status=status, created_dt=created_dt, bank_ref=bank_ref,
                   refund_of=refund_of)
        self.platform[key] = row
        return row

    def add_bank(self, utr, amount_p, cd, value_dt, narration, batch_id=None,
                 status="SUCCESS"):
        self._b_seq += 1
        key = f"B{self._b_seq:05d}"
        row = dict(key=key, utr=utr, amount_p=amount_p, cd=cd,
                   value_dt=value_dt, narration=narration, batch_id=batch_id,
                   status=status)
        self.bank[key] = row
        return row

    def group(self, category, type_, p_rows, b_rows, description, resolution,
              roles=None, related=None, counterparts=None):
        self.groups.append(dict(
            category=category, type=type_,
            p=[r["key"] for r in p_rows], b=[r["key"] for r in b_rows],
            description=description, resolution=resolution,
            roles=roles or {}, related=related or [],
            cps=counterparts or {}))

    def _pay(self, d0, d1, amount_p=None, method=None, fractional=None,
             lo=None, hi=None, with_ref=True, status="SUCCESS", created=None):
        method = method or self.rng.choices(METHODS, METHOD_WEIGHTS)[0]
        if amount_p is None:
            amount_p = self.rand_amount(lo, hi, fractional)
        if created is None:
            created = self.rand_created(d0, d1)
        utr = self.new_utr(method)
        p = self.add_platform(self.new_order(), self.new_customer(), amount_p,
                              method, "PAYMENT", status, created,
                              utr if with_ref else None)
        p["utr"] = utr  # internal only, not written to the platform CSV
        return p

    def _bank_for(self, p, lag=None, amount_p=None, status="SUCCESS",
                  include_order=True, value_dt=None, suffix=""):
        if value_dt is None:
            lag = lag if lag is not None else self.clean_lag()
            value_dt = self.settle_dt(p["created_dt"], lag)
        narr = f"PAYGATE SETTLEMENT/{p['method']}"
        if include_order:
            narr += f"/{p['order_id']}"
        narr += suffix
        amt = p["amount_p"] if amount_p is None else amount_p
        return self.add_bank(p["utr"], amt, "CREDIT", value_dt, narr, None,
                             status)

    @staticmethod
    def _lag(p, b):
        return (b["value_dt"].date() - p["created_dt"].date()).days

    # ================================================================ scenarios
    def s_clean(self):
        p = self._pay(1, 28)
        b = self._bank_for(p)
        self.group("MATCHED", "CLEAN_MATCH", [p], [b],
                   f"Platform and bank agree on {inr(p['amount_p'])}; settled "
                   f"T+{self._lag(p, b)} with matching UTR and order id.",
                   "None - should auto-match 1:1.")

    # ---- timing -------------------------------------------------------
    def s_month_end_cutoff(self):
        day = self.rng.choice([29, 30])
        lag = 2 if day == 29 else self.rng.choice([1, 2])
        p = self._pay(day, day)
        b = self._bank_for(p, lag=lag)
        self.group(
            "TIMING", "TIMING_MONTH_END_CUTOFF", [p], [b],
            f"Platform books {inr(p['amount_p'])} on {p['created_dt']:%d-%b} "
            f"(November) but the bank value date is {b['value_dt']:%d-%b} "
            f"(December). Amounts agree; at the 30-Nov cut-off the platform "
            f"is ahead of the bank by this amount.",
            "Timing difference - show as 'in transit' on the November "
            "reconciliation; clears when the bank credit lands in December.")

    def s_weekend_lag(self):
        day = self.rng.choice([6, 7, 13, 14, 20, 21, 27])  # Fridays/Saturdays
        p = self._pay(day, day)
        b = self._bank_for(p, lag=3)
        self.group(
            "TIMING", "TIMING_WEEKEND_LAG", [p], [b],
            f"Created on {p['created_dt']:%A %d-%b}; bank settled "
            f"{self._lag(p, b)} days later on {b['value_dt']:%A %d-%b}, "
            f"outside the normal 1-2 day window because of weekend / bank "
            f"holiday processing. Amounts agree.",
            "Late-but-valid settlement. Auto-clears; flag as an SLA/window "
            "breach, not a missing payment.")

    def s_prior_period_spillover(self):
        method = self.rng.choice(["UPI", "CARD"])
        amt = self.rand_amount()
        utr = self.new_utr(method)
        old_order = self.new_order(prior=True)
        vdt = self.settle_dt(datetime(2026, 11, self.rng.choice([1, 2])), 0)
        b = self.add_bank(utr, amt, "CREDIT", vdt,
                          f"PAYGATE SETTLEMENT/{method}/{old_order}")
        self.group(
            "TIMING", "TIMING_PRIOR_PERIOD_SPILLOVER", [], [b],
            f"Bank credit of {inr(amt)} on {vdt:%d-%b} belongs to an October "
            f"transaction (order {old_order}, earlier order-number series) "
            f"that the platform booked in October. It has no November "
            f"platform row - the mirror image of the month-end cut-off.",
            "Match against the October platform file; no action in November "
            "other than listing it as a prior-period item.")

    # ---- amount mismatches -------------------------------------------
    def s_fee_deduction(self):
        p = self._pay(1, 27, lo=500, hi=49999)
        amt = p["amount_p"]
        fee = (amt * MDR_PCT + 50) // 100
        gst = (fee * GST_PCT + 50) // 100
        net = amt - fee - gst
        b = self._bank_for(p, amount_p=net)
        self.group(
            "AMOUNT", "AMOUNT_FEE_DEDUCTION", [p], [b],
            f"Bank deducted gateway MDR {MDR_PCT}% ({inr(fee)}) plus "
            f"{GST_PCT}% GST on the fee ({inr(gst)}). Platform expected "
            f"{inr(amt)}, bank credited {inr(net)}; shortfall "
            f"{inr(fee + gst)}.",
            "Not a missing payment. Book MDR and GST as expenses and adjust "
            "the platform receivable.")

    def s_rounding_diff(self):
        p = self._pay(1, 27, fractional=True)
        delta = self.rng.choice([-2, -1, 1, 2])
        b = self._bank_for(p, amount_p=p["amount_p"] + delta)
        self.group(
            "AMOUNT", "AMOUNT_ROUNDING", [p], [b],
            f"Paise-level rounding difference: platform {inr(p['amount_p'])}, "
            f"bank {inr(b['amount_p'])} ({delta:+d} paise).",
            "Within tolerance. Auto-match with a rounding threshold "
            "(e.g. +/- INR 0.05) and post the residual to a rounding account.")

    def s_partial_settlement(self):
        p = self._pay(1, 27, lo=1000, hi=49999)
        pct = self.rng.randint(50, 90)
        part = p["amount_p"] * pct // 100
        b = self._bank_for(p, amount_p=part, suffix="/PARTIAL")
        self.group(
            "AMOUNT", "AMOUNT_PARTIAL_SETTLEMENT", [p], [b],
            f"Bank settled only {pct}% ({inr(part)}) of the platform amount "
            f"{inr(p['amount_p'])}; the remaining {inr(p['amount_p'] - part)} "
            f"has not arrived.",
            "Raise a claim with the gateway/bank for the balance; keep the "
            "difference open as a receivable.")

    def s_wrong_amount(self):
        p = self._pay(1, 27, lo=1000, hi=49999, fractional=False)
        rupees, paise = divmod(p["amount_p"], 100)
        s = str(rupees)
        idx = [i for i in range(len(s) - 1)
               if s[i] != s[i + 1] and not (i == 0 and s[1] == "0")]
        if idx:
            i = self.rng.choice(idx)
            t = list(s)
            t[i], t[i + 1] = t[i + 1], t[i]
            new_rupees = int("".join(t))
        else:
            new_rupees = rupees + 100
        wrong = new_rupees * 100 + paise
        b = self._bank_for(p, amount_p=wrong)
        self.group(
            "AMOUNT", "AMOUNT_WRONG_AMOUNT", [p], [b],
            f"Keying/transposition error: platform {inr(p['amount_p'])}, "
            f"bank {inr(wrong)} (digits swapped). Difference "
            f"{inr(p['amount_p'] - wrong)}; the UTR and order id match, so "
            f"this is the same transaction with a wrong amount.",
            "Investigate with the bank; correct whichever side is wrong and "
            "settle the difference.")

    # ---- missing records ---------------------------------------------
    def s_missing_in_bank(self):
        p = self._pay(1, 27, with_ref=False)
        self.group(
            "MISSING", "MISSING_IN_BANK", [p], [],
            f"Platform captured {inr(p['amount_p'])} on "
            f"{p['created_dt']:%d-%b}, but no bank credit exists even after "
            f"the 2-day window plus buffer - the settlement never arrived.",
            "Escalate to the gateway/bank with the transaction id; keep as "
            "an open receivable. Do not write off.")

    def s_missing_in_platform(self):
        method = self.rng.choice(["UPI", "NETBANKING"])
        amt = self.rand_amount()
        utr = self.new_utr(method)
        vdt = self.settle_dt(datetime(2026, 11, self.rng.randint(3, 30)), 0)
        rail = "UPI" if method == "UPI" else "NEFT"
        b = self.add_bank(utr, amt, "CREDIT", vdt,
                          f"{rail}/{utr}/DIRECT CUSTOMER TRANSFER - NO ORDER REF")
        self.group(
            "MISSING", "MISSING_IN_PLATFORM", [], [b],
            f"Unexpected bank credit of {inr(amt)} on {vdt:%d-%b} with no "
            f"order reference - a customer paid directly to the bank account "
            f"outside the platform, or it is an unidentified credit.",
            "Identify the remitter, then either create the platform record "
            "or refund the customer. Park in suspense meanwhile.")

    # ---- duplicates --------------------------------------------------
    def s_duplicate_platform(self):
        p1 = self._pay(1, 27)
        p2 = self.add_platform(
            p1["order_id"], p1["customer_id"], p1["amount_p"], p1["method"],
            "PAYMENT", "SUCCESS",
            p1["created_dt"] + timedelta(seconds=self.rng.randint(2, 45)),
            p1["bank_ref"])
        b = self._bank_for(p1)
        self.group(
            "DUPLICATE", "DUPLICATE_PLATFORM", [p1, p2], [b],
            f"Webhook retry created a second platform row for the same order "
            f"{p1['order_id']} seconds after the first. The bank credited "
            f"only once, so the platform is overstated by "
            f"{inr(p1['amount_p'])}.",
            "Void the duplicate platform row; no bank action needed.",
            roles={p1["key"]: "PRIMARY", p2["key"]: "DUPLICATE"})

    def s_duplicate_bank(self):
        p = self._pay(1, 27)
        b1 = self._bank_for(p)
        b2 = self.add_bank(b1["utr"], b1["amount_p"], "CREDIT",
                           b1["value_dt"] + timedelta(
                               hours=self.rng.randint(1, 20)),
                           b1["narration"], None, "SUCCESS")
        self.group(
            "DUPLICATE", "DUPLICATE_BANK", [p], [b1, b2],
            f"Bank posted the same credit (UTR {b1['utr']}) twice for "
            f"{inr(p['amount_p'])}; the platform recorded it once, so the "
            f"bank is higher by {inr(p['amount_p'])}.",
            "Ask the bank to reverse or confirm the duplicate posting; "
            "hold the extra amount as a payable.",
            roles={b1["key"]: "PRIMARY", b2["key"]: "DUPLICATE"})

    def s_same_amount_same_day(self):
        amount = self.rand_amount(lo=300, hi=4999, fractional=False)
        day = self.rng.randint(1, 27)
        c1 = self.rand_created(day, day)
        c2 = c1 + timedelta(minutes=self.rng.randint(45, 180))
        p1 = self._pay(day, day, amount_p=amount, method="UPI", created=c1)
        p2 = self._pay(day, day, amount_p=amount, method="UPI", created=c2)
        lag = self.clean_lag()
        t = sorted([self.settle_dt(c1, lag), self.settle_dt(c1, lag)])
        b2 = self._bank_for(p2, value_dt=t[0])  # bank posts in reverse order
        b1 = self._bank_for(p1, value_dt=t[1])
        self.group(
            "DUPLICATE", "SAME_AMOUNT_SAME_DAY", [p1, p2], [b1, b2],
            f"Two different orders for exactly {inr(amount)} on the same "
            f"day. Both are legitimate and both settled, but the bank posted "
            f"them in reverse order. A matcher using amount + date alone "
            f"will pair them ambiguously or wrongly.",
            "Match on UTR / order id, never on amount + date alone. No "
            "financial gap.",
            counterparts={p1["key"]: [b1["key"]], p2["key"]: [b2["key"]],
                          b1["key"]: [p1["key"]], b2["key"]: [p2["key"]]})

    # ---- status mismatches -------------------------------------------
    def _status_case(self, kind):
        cfg = {
            "SUCCESS_BANK_FAILED": (
                "SUCCESS", "FAILED", True, "/RETURNED",
                "STATUS_PLATFORM_SUCCESS_BANK_FAILED",
                "Platform marked the payment SUCCESS ({a}) but the bank "
                "settlement leg FAILED / was returned. No money arrived.",
                "Re-initiate or recover the settlement; reverse the "
                "platform revenue until cash is received."),
            "SUCCESS_BANK_REVERSED": (
                "SUCCESS", "REVERSED", True, "/REVERSAL",
                "STATUS_PLATFORM_SUCCESS_BANK_REVERSED",
                "Platform shows SUCCESS ({a}) but the bank credit was "
                "REVERSED after posting, so net cash is zero.",
                "Find the reversal reason with the bank; reverse the "
                "platform entry or re-collect."),
            "FAILED_BANK_SUCCESS": (
                "FAILED", "SUCCESS", False, "",
                "STATUS_PLATFORM_FAILED_BANK_SUCCESS",
                "Platform marked the payment FAILED but the bank credited "
                "{a}. The customer was charged; the platform status is "
                "wrong or stale.",
                "Correct the platform status to SUCCESS (or refund the "
                "customer if the order was cancelled)."),
            "PENDING_BANK_SUCCESS": (
                "PENDING", "SUCCESS", False, "",
                "STATUS_PLATFORM_PENDING_BANK_SUCCESS",
                "Platform status is stuck at PENDING (missed callback) while "
                "the bank already credited {a}.",
                "Run a status-sync job; move the platform row to SUCCESS."),
        }
        p_status, b_status, with_ref, suffix, atype, desc, res = cfg[kind]
        p = self._pay(1, 27, status=p_status, with_ref=with_ref)
        b = self._bank_for(p, status=b_status, suffix=suffix)
        self.group("STATUS", atype, [p], [b],
                   desc.format(a=inr(p["amount_p"])), res)

    def s_status_platform_success_bank_failed(self):
        self._status_case("SUCCESS_BANK_FAILED")

    def s_status_platform_success_bank_reversed(self):
        self._status_case("SUCCESS_BANK_REVERSED")

    def s_status_platform_failed_bank_success(self):
        self._status_case("FAILED_BANK_SUCCESS")

    def s_status_platform_pending_bank_success(self):
        self._status_case("PENDING_BANK_SUCCESS")

    # ---- refunds and reversals ---------------------------------------
    def s_refund_processed(self):
        p = self._pay(1, 20)
        b = self._bank_for(p)
        self.group("MATCHED", "CLEAN_MATCH", [p], [b],
                   f"Platform and bank agree on {inr(p['amount_p'])}. This "
                   f"payment was later refunded (see the linked refund "
                   f"group).", "None - should auto-match 1:1.")
        created = p["created_dt"] + timedelta(
            days=self.rng.randint(2, 4), seconds=self.rng.randint(0, 10800))
        full = self.rng.random() < 0.5
        ref_amt = (p["amount_p"] if full
                   else p["amount_p"] * self.rng.randint(30, 80) // 100)
        ref_utr = self.new_utr(p["method"])
        r = self.add_platform(p["order_id"], p["customer_id"], -ref_amt,
                              p["method"], "REFUND", "SUCCESS", created,
                              ref_utr, refund_of=p["key"])
        bd = self.add_bank(ref_utr, ref_amt, "DEBIT",
                           self.settle_dt(created, self.clean_lag()),
                           f"REFUND/{p['order_id']}")
        kind = "full" if full else "partial"
        self.group(
            "REFUND_REVERSAL", "REFUND_PROCESSED", [r], [bd],
            f"Legitimate {kind} refund of {inr(ref_amt)}. Platform stores it "
            f"as {inr(-ref_amt)}; bank shows a positive {inr(ref_amt)} DEBIT. "
            f"Amounts agree once the sign convention is normalised.",
            "Match with sign inversion and link to the original payment. "
            "No financial gap.",
            related=[p["key"]])

    def s_refund_no_original(self):
        method = self.rng.choice(METHODS)
        amt = self.rand_amount()
        self._orphan_seq += 1
        ghost = f"PTX{9000 + self._orphan_seq:07d}"
        ref_utr = self.new_utr(method)
        order = self.new_order(prior=True)
        created = self.rand_created(1, 27)
        r = self.add_platform(order, self.new_customer(), -amt, method,
                              "REFUND", "SUCCESS", created, ref_utr,
                              refund_of=ghost)
        bd = self.add_bank(ref_utr, amt, "DEBIT",
                           self.settle_dt(created, self.clean_lag()),
                           f"REFUND/{order}")
        self.group(
            "REFUND_REVERSAL", "REFUND_NO_ORIGINAL", [r], [bd],
            f"Refund of {inr(amt)} references original transaction {ghost}, "
            f"which does not exist in the platform file (prior-period "
            f"payment, or an invalid / fraudulent refund). Platform and bank "
            f"amounts agree, so only a referential check catches it.",
            "Trace the original payment (likely October); if none exists, "
            "treat as a suspicious refund and investigate.")

    def s_chargeback(self):
        p = self._pay(1, 18)
        b = self._bank_for(p)
        self.group("MATCHED", "CLEAN_MATCH", [p], [b],
                   f"Platform and bank agree on {inr(p['amount_p'])}. This "
                   f"payment was later charged back (see the linked "
                   f"chargeback group).", "None - should auto-match 1:1.")
        vdt = b["value_dt"] + timedelta(days=self.rng.randint(5, 8),
                                        hours=self.rng.randint(0, 3))
        cb = self.add_bank(self.new_utr("CARD"), p["amount_p"], "DEBIT", vdt,
                           f"CHARGEBACK/DISPUTE/{p['utr']}")
        self.group(
            "REFUND_REVERSAL", "CHARGEBACK_NOT_IN_PLATFORM", [], [cb],
            f"Bank debited {inr(p['amount_p'])} on {vdt:%d-%b} as a customer "
            f"dispute/chargeback against UTR {p['utr']}. The platform has "
            f"not recorded the dispute, so its revenue is overstated.",
            "Record the chargeback in the platform; respond to the dispute "
            "within the network deadline.",
            related=[p["key"]])

    # ---- batching ----------------------------------------------------
    def s_batch_settlement(self, size, idx):
        method = self.rng.choice(["UPI", "CARD"])
        d = self.rng.randint(3, 22)
        ps = [self._pay(d, d + 1, method=method, with_ref=False)
              for _ in range(size)]
        last = max(p["created_dt"] for p in ps)
        vdt = self.settle_dt(last, self.clean_lag())
        total = sum(p["amount_p"] for p in ps)
        batch_id = f"BATCH-{vdt:%Y%m%d}-{idx:02d}"
        b = self.add_bank(self.new_utr("CARD"), total, "CREDIT", vdt,
                          f"PAYGATE BATCH SETTLEMENT/{batch_id}/{size} TXNS",
                          batch_id, "SUCCESS")
        roles = {p["key"]: "BATCH_MEMBER" for p in ps}
        roles[b["key"]] = "BATCH_CREDIT"
        self.group(
            "BATCH", "BATCH_SETTLEMENT", ps, [b],
            f"{size} platform transactions ({method}) were settled as ONE "
            f"lump-sum bank credit of {inr(total)} ({batch_id}). No platform "
            f"row has a bank reference; the sum of the members equals the "
            f"credit exactly.",
            "One-to-many match: group platform rows by method and date "
            "window and find the subset whose sum equals the credit.",
            roles=roles)

    # ---- reference / identifier problems -----------------------------
    def _ref_case(self, kind):
        if kind == "MISSING":
            p = self._pay(1, 27, with_ref=False, fractional=True)
            b = self._bank_for(p, include_order=False)
            atype = "REF_MISSING"
            desc = (f"Platform has no bank reference and the bank narration "
                    f"carries no order id. The only way to pair them is "
                    f"amount ({inr(p['amount_p'])}) plus the settlement "
                    f"window.")
            res = ("Fuzzy match on amount + date; then back-fill the UTR on "
                   "the platform row.")
        elif kind == "TRUNCATED":
            p = self._pay(1, 27)
            p["bank_ref"] = p["utr"][:8]
            b = self._bank_for(p)
            atype = "REF_TRUNCATED"
            desc = (f"Platform bank_ref '{p['bank_ref']}' is truncated; the "
                    f"full bank UTR is '{b['utr']}'. The order id in the "
                    f"narration still identifies the pair.")
            res = "Match on UTR prefix or order id; fix the truncation upstream."
        else:
            p = self._pay(1, 27)
            u = p["utr"]
            if u.isdigit():
                p["bank_ref"] = "UTR-" + " ".join([u[:4], u[4:8], u[8:]])
            else:
                p["bank_ref"] = u.lower() + " "
            b = self._bank_for(p)
            atype = "REF_FORMAT_MISMATCH"
            desc = (f"Platform bank_ref '{p['bank_ref']}' differs from bank "
                    f"UTR '{b['utr']}' only by case, spaces or a prefix. "
                    f"Same transaction.")
            res = "Normalise IDs (strip, upper-case, remove prefixes) before matching."
        self.group("REFERENCE", atype, [p], [b], desc, res)

    def s_ref_missing(self):
        self._ref_case("MISSING")

    def s_ref_truncated(self):
        self._ref_case("TRUNCATED")

    def s_ref_format_mismatch(self):
        self._ref_case("FORMAT")

    # ================================================================== build
    def build(self):
        for name, n in SCENARIO_COUNTS.items():
            if name == "batch_settlement":
                for i, size in enumerate(BATCH_SIZES, 1):
                    self.s_batch_settlement(size, i)
                continue
            fn = getattr(self, f"s_{name}")
            for _ in range(n):
                fn()
        n_clean = N_PLATFORM_ROWS - len(self.platform)
        assert n_clean >= 0, "Anomaly scenarios exceed the platform row budget"
        for _ in range(n_clean):
            self.s_clean()

    # ================================================================ finalize
    def finalize(self):
        plat = sorted(self.platform.values(),
                      key=lambda r: (r["created_dt"], r["key"]))
        bank = sorted(self.bank.values(),
                      key=lambda r: (r["value_dt"], r["key"]))
        idmap = {r["key"]: f"PTX{i:07d}" for i, r in enumerate(plat, 1)}
        idmap.update({r["key"]: f"BNK{i:07d}" for i, r in enumerate(bank, 1)})

        for g in self.groups:
            prow = [self.platform[k] for k in g["p"]]
            brow = [self.bank[k] for k in g["b"]]
            g["p_eff"] = sum(eff_platform(r) for r in prow)
            g["b_eff"] = sum(eff_bank(r) for r in brow)
            g["p_cut"] = sum(eff_platform(r) for r in prow
                             if r["created_dt"] <= CUTOFF)
            g["b_cut"] = sum(eff_bank(r) for r in brow
                             if r["value_dt"] <= CUTOFF)
            g["start"] = min([r["created_dt"] for r in prow]
                             + [r["value_dt"] for r in brow])
            if prow and brow:
                g["lag"] = (min(r["value_dt"] for r in brow).date()
                            - max(r["created_dt"] for r in prow).date()).days
            else:
                g["lag"] = ""
        self.groups.sort(key=lambda g: (g["start"], (g["p"] + g["b"])[0]))
        for i, g in enumerate(self.groups, 1):
            g["id"] = f"G{i:04d}"

        truth = []
        for g in self.groups:
            for src, keys, table in (("PLATFORM", g["p"], self.platform),
                                     ("BANK", g["b"], self.bank)):
                for k in keys:
                    r = table[k]
                    if src == "PLATFORM":
                        amt, other = r["amount_p"], g["b"]
                    else:
                        amt = r["amount_p"] if r["cd"] == "CREDIT" else -r["amount_p"]
                        other = g["p"]
                    cps = g["cps"].get(k, other)
                    truth.append({
                        "group_id": g["id"],
                        "record_source": src,
                        "record_id": idmap[k],
                        "record_role": g["roles"].get(k, "PRIMARY"),
                        "anomaly_category": g["category"],
                        "anomaly_type": g["type"],
                        "is_anomaly": g["type"] != "CLEAN_MATCH",
                        "expected_counterpart_ids": ";".join(idmap[c] for c in cps),
                        "related_record_ids": ";".join(idmap.get(c, c) for c in g["related"]),
                        "record_amount_inr": fmt_amount(amt),
                        "group_platform_inr": fmt_amount(g["p_eff"]),
                        "group_bank_inr": fmt_amount(g["b_eff"]),
                        "gap_final_inr": fmt_amount(g["p_eff"] - g["b_eff"]),
                        "gap_at_cutoff_inr": fmt_amount(g["p_cut"] - g["b_cut"]),
                        "settlement_lag_days": g["lag"],
                        "root_cause": g["description"],
                        "expected_resolution": g["resolution"],
                    })
        return plat, bank, idmap, truth

    # ================================================================== write
    def write(self, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        plat, bank, idmap, truth = self.finalize()
        self.validate(plat, bank, idmap, truth)

        with open(out_dir / "platform_transactions.csv", "w", newline="",
                  encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(PLATFORM_COLS)
            for r in plat:
                w.writerow([
                    idmap[r["key"]], r["order_id"], r["customer_id"],
                    fmt_amount(r["amount_p"]), "INR", r["method"],
                    r["txn_type"], r["status"],
                    r["created_dt"].strftime(DT_FMT), r["bank_ref"] or "",
                    idmap.get(r["refund_of"], r["refund_of"] or ""),
                ])
        with open(out_dir / "bank_transactions.csv", "w", newline="",
                  encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(BANK_COLS)
            for r in bank:
                w.writerow([
                    idmap[r["key"]], r["utr"], fmt_amount(r["amount_p"]),
                    r["cd"], r["value_dt"].strftime(DT_FMT), r["narration"],
                    r["batch_id"] or "", r["status"],
                ])
        with open(out_dir / "ground_truth.csv", "w", newline="",
                  encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=TRUTH_COLS)
            w.writeheader()
            w.writerows(truth)
        self.print_summary(plat, bank)

    # ============================================================== validation
    def validate(self, plat, bank, idmap, truth):
        assert len(plat) == N_PLATFORM_ROWS, len(plat)
        assert len({idmap[r["key"]] for r in plat}) == len(plat)
        assert len({idmap[r["key"]] for r in bank}) == len(bank)
        ids = [t["record_id"] for t in truth]
        assert len(ids) == len(set(ids)), "record appears in two groups"
        assert set(ids) == {idmap[r["key"]] for r in plat + bank}, \
            "every record must appear in ground truth exactly once"
        for t in truth:
            if t["anomaly_type"] == "CLEAN_MATCH":
                assert t["settlement_lag_days"] in (1, 2), t
        # group-level cut-off gaps must add up to the direct calculation
        direct = (sum(eff_platform(r) for r in plat
                      if r["created_dt"] <= CUTOFF)
                  - sum(eff_bank(r) for r in bank if r["value_dt"] <= CUTOFF))
        grouped = sum(g["p_cut"] - g["b_cut"] for g in self.groups)
        assert direct == grouped, (direct, grouped)

    # ================================================================ summary
    def print_summary(self, plat, bank):
        rows = OrderedDict()
        for g in self.groups:
            s = rows.setdefault(g["type"], dict(g=0, p=0, b=0, cut=0, fin=0))
            s["g"] += 1
            s["p"] += len(g["p"])
            s["b"] += len(g["b"])
            s["cut"] += g["p_cut"] - g["b_cut"]
            s["fin"] += g["p_eff"] - g["b_eff"]
        print(f"\nPlatform rows: {len(plat)}   Bank rows: {len(bank)}   "
              f"Groups: {len(self.groups)}\n")
        print(f"{'anomaly_type':42}{'groups':>7}{'plat':>6}{'bank':>6}"
              f"{'gap@30-Nov':>16}{'final gap':>16}")
        print("-" * 93)
        for t, s in sorted(rows.items(), key=lambda kv: -kv[1]["g"]):
            print(f"{t:42}{s['g']:>7}{s['p']:>6}{s['b']:>6}"
                  f"{fmt_amount(s['cut']):>16}{fmt_amount(s['fin']):>16}")
        tot_cut = sum(s["cut"] for s in rows.values())
        tot_fin = sum(s["fin"] for s in rows.values())
        print("-" * 93)
        print(f"{'TOTAL (platform minus bank, INR)':42}{'':>19}"
              f"{fmt_amount(tot_cut):>16}{fmt_amount(tot_fin):>16}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args()
    builder = DatasetBuilder(args.seed)
    builder.build()
    builder.write(Path(args.out_dir))


if __name__ == "__main__":
    main()
