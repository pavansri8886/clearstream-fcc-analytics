"""
detectors.py
------------
AML rule-based detectors. Each detector finds one type of fraud.
All detectors receive a pandas DataFrame and return list[AlertRecord].

Thresholds are loaded from config/settings.yaml — no hardcoding.

Detectors:
  1. StructuringDetector       — splitting amounts to stay below reporting limit
  2. VelocityDetector          — too many transactions in a short window
  3. LargeTransactionDetector  — single transaction above threshold
  4. HighRiskCorridorDetector  — transaction involving a FATF high-risk country
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config import CFG
from schema import AlertRecord, determine_severity, _safe_float, _safe_str

# Load FATF high-risk countries from settings.yaml
FATF_HIGH_RISK = set(CFG["sanctions_screening"]["high_risk_countries"])


def _cluster_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


class StructuringDetector:
    """
    Detects structuring (smurfing):
    3+ transactions just below the EUR 10k reporting threshold
    from the same sender within a 72-hour window.
    """

    def __init__(self):
        cfg = CFG["aml_rules"]["structuring"]
        self.THRESHOLD_HIGH = cfg["threshold_eur"]       # e.g. 9999
        self.THRESHOLD_LOW  = 5_000                      # lower bound
        self.MIN_COUNT      = cfg["min_transactions"]    # e.g. 3
        self.WINDOW_HOURS   = cfg["window_hours"]        # e.g. 72

    def detect(self, df: pd.DataFrame) -> list[AlertRecord]:
        if df.empty or "amount_eur" not in df.columns:
            return []

        sub = df[
            df["amount_eur"].apply(_safe_float).between(self.THRESHOLD_LOW, self.THRESHOLD_HIGH)
        ].copy()

        if sub.empty:
            return []

        sub["_ts"]     = pd.to_datetime(sub["timestamp"], errors="coerce")
        sub["_amount"] = sub["amount_eur"].apply(_safe_float)
        sub["_sender"] = sub["sender_name"].apply(_safe_str)
        sub = sub.dropna(subset=["_ts"]).sort_values("_ts")  # drop unparseable timestamps

        alerts = []
        window = f"{self.WINDOW_HOURS}h"

        for sender, group in sub.groupby("_sender"):
            group = group.set_index("_ts").sort_index()

            # Rolling count replaces the old O(n²) nested loop
            counts = group.rolling(window)["_amount"].count()
            qualifying = counts[counts >= self.MIN_COUNT]
            if qualifying.empty:
                continue

            seen_days: set = set()
            for ts in qualifying.index:
                day = ts.date()
                if day in seen_days:
                    continue
                seen_days.add(day)

                txns = group.loc[ts - pd.Timedelta(hours=self.WINDOW_HOURS): ts]
                if len(txns) < self.MIN_COUNT:
                    continue

                cid   = _cluster_id("STR")
                total = txns["_amount"].sum()

                for _, txn in txns.iterrows():
                    alerts.append(AlertRecord(
                        transaction_id=_safe_str(txn.get("transaction_id")),
                        message_type="MT103",
                        alert_type="STRUCTURING",
                        alert_severity=determine_severity("STRUCTURING", _safe_float(txn.get("amount_eur"))),
                        aml_typology="STRUCTURING",
                        amount_eur=_safe_float(txn.get("amount_eur")),
                        currency=_safe_str(txn.get("currency", "EUR")),
                        booking_date=_safe_str(txn.get("booking_date")),
                        sender_name=_safe_str(txn.get("sender_name")),
                        sender_country=_safe_str(txn.get("sender_country")),
                        receiver_name=_safe_str(txn.get("receiver_name")),
                        receiver_country=_safe_str(txn.get("receiver_country")),
                        cluster_id=cid,
                        description=(
                            f"Structuring: {len(txns)} transactions "
                            f"EUR {self.THRESHOLD_LOW:,}-{self.THRESHOLD_HIGH:,} "
                            f"from '{sender}' in {self.WINDOW_HOURS}h. "
                            f"Total: EUR {total:,.2f}"
                        ),
                    ))

        return alerts


class VelocityDetector:
    """
    Detects abnormal transaction speed.
    Flags if the same sender sends 20+ transactions within 1 hour.
    """

    def __init__(self):
        self.MAX_PER_HOUR = CFG["aml_rules"]["velocity"]["max_transactions_per_hour"]

    def detect(self, df: pd.DataFrame) -> list[AlertRecord]:
        if df.empty or "sender_name" not in df.columns:
            return []

        df = df.copy()
        df["_ts"]     = pd.to_datetime(df["timestamp"], errors="coerce")
        df["_sender"] = df["sender_name"].apply(_safe_str)
        df["_amount"] = df["amount_eur"].apply(_safe_float) if "amount_eur" in df.columns else 0
        df = df.dropna(subset=["_ts"]).sort_values("_ts")  # drop unparseable timestamps

        alerts = []

        for sender, group in df.groupby("_sender"):
            group = group.set_index("_ts").sort_index()

            counts = group.rolling("1h")["_amount"].count()
            qualifying = counts[counts >= self.MAX_PER_HOUR]
            if qualifying.empty:
                continue

            seen_hours: set = set()
            for ts in qualifying.index:
                hour_key = ts.strftime("%Y%m%d%H")
                if hour_key in seen_hours:
                    continue
                seen_hours.add(hour_key)

                txns = group.loc[ts - pd.Timedelta(hours=1): ts]
                if len(txns) < self.MAX_PER_HOUR:
                    continue

                cid   = _cluster_id("VEL")
                total = txns["_amount"].sum()

                for _, txn in txns.head(5).iterrows():
                    alerts.append(AlertRecord(
                        transaction_id=_safe_str(txn.get("transaction_id")),
                        message_type=_safe_str(txn.get("message_type", "MT103")),
                        alert_type="VELOCITY_ABUSE",
                        alert_severity=determine_severity("VELOCITY_ABUSE", _safe_float(txn.get("amount_eur"))),
                        aml_typology="VELOCITY_ABUSE",
                        amount_eur=_safe_float(txn.get("amount_eur")),
                        currency=_safe_str(txn.get("currency", "EUR")),
                        booking_date=_safe_str(txn.get("booking_date")),
                        sender_name=_safe_str(txn.get("sender_name")),
                        sender_country=_safe_str(txn.get("sender_country")),
                        receiver_name=_safe_str(txn.get("receiver_name")),
                        receiver_country=_safe_str(txn.get("receiver_country")),
                        cluster_id=cid,
                        description=(
                            f"Velocity: '{sender}' sent {len(txns)} transactions "
                            f"in 1 hour (limit: {self.MAX_PER_HOUR}). "
                            f"Total: EUR {total:,.2f}"
                        ),
                    ))

        return alerts


class LargeTransactionDetector:
    """
    Flags single large transactions:
    - >= EUR 1M → HIGH severity
    - >= EUR 100k to/from a FATF high-risk country → MEDIUM severity
    """

    def __init__(self):
        cfg = CFG["aml_rules"]["large_transaction"]
        self.LARGE     = cfg["threshold_eur"]           # e.g. 1_000_000
        self.HIGH_RISK = cfg["high_risk_threshold_eur"] # e.g. 100_000

    def detect(self, df: pd.DataFrame) -> list[AlertRecord]:
        if df.empty:
            return []

        # Vectorised filter first — iterrows only touches flagged rows
        amounts = df["amount_eur"].apply(_safe_float)
        is_hr   = (df["sender_country"].isin(FATF_HIGH_RISK) |
                   df["receiver_country"].isin(FATF_HIGH_RISK))
        flagged = df[(amounts >= self.LARGE) |
                     ((amounts >= self.HIGH_RISK) & is_hr)]

        alerts = []
        for _, row in flagged.iterrows():
            amount = _safe_float(row.get("amount_eur"))
            sc     = _safe_str(row.get("sender_country"))
            rc     = _safe_str(row.get("receiver_country"))
            hr_c   = sc if sc in FATF_HIGH_RISK else (rc if rc in FATF_HIGH_RISK else "")
            bdate  = _safe_str(row.get("booking_date"))
            msg    = _safe_str(row.get("message_type", "MT103"))

            if amount >= self.LARGE:
                alerts.append(AlertRecord(
                    transaction_id=_safe_str(row.get("transaction_id")),
                    message_type=msg,
                    alert_type="LARGE_TRANSACTION",
                    alert_severity=determine_severity("LARGE_TRANSACTION", amount),
                    aml_typology="LARGE_TRANSACTION",
                    amount_eur=amount,
                    currency=_safe_str(row.get("currency", "EUR")),
                    booking_date=bdate,
                    sender_name=_safe_str(row.get("sender_name")),
                    sender_country=sc,
                    receiver_name=_safe_str(row.get("receiver_name")),
                    receiver_country=rc,
                    description=f"Large transaction: EUR {amount:,.2f} exceeds EUR {self.LARGE:,} threshold.",
                ))
            elif hr_c:
                alerts.append(AlertRecord(
                    transaction_id=_safe_str(row.get("transaction_id")),
                    message_type=msg,
                    alert_type="HIGH_RISK_CORRIDOR",
                    alert_severity="MEDIUM",
                    aml_typology="HIGH_RISK_JURISDICTION",
                    amount_eur=amount,
                    currency=_safe_str(row.get("currency", "EUR")),
                    booking_date=bdate,
                    sender_name=_safe_str(row.get("sender_name")),
                    sender_country=sc,
                    receiver_name=_safe_str(row.get("receiver_name")),
                    receiver_country=rc,
                    description=f"High-risk corridor: EUR {amount:,.2f} involving FATF country '{hr_c}'.",
                ))
        return alerts


class HighRiskCorridorDetector:
    """
    Flags any transaction where the sender or receiver country
    is on the FATF high-risk list.
    """

    def detect(self, df: pd.DataFrame) -> list[AlertRecord]:
        if df.empty:
            return []

        # Vectorised filter — only iterate rows with a high-risk country
        flagged = df[
            df["sender_country"].isin(FATF_HIGH_RISK) |
            df["receiver_country"].isin(FATF_HIGH_RISK)
        ]

        alerts = []
        for _, row in flagged.iterrows():
            sc    = _safe_str(row.get("sender_country"))
            rc    = _safe_str(row.get("receiver_country"))
            hr_c  = sc if sc in FATF_HIGH_RISK else (rc if rc in FATF_HIGH_RISK else None)
            if not hr_c:
                continue

            amount = _safe_float(row.get("amount_eur"))
            msg    = _safe_str(row.get("message_type", "MT103"))

            alerts.append(AlertRecord(
                transaction_id=_safe_str(row.get("transaction_id")),
                message_type=msg,
                alert_type="HIGH_RISK_CORRIDOR",
                alert_severity="MEDIUM",
                aml_typology="HIGH_RISK_JURISDICTION",
                amount_eur=amount,
                currency=_safe_str(row.get("currency", "EUR")),
                booking_date=_safe_str(row.get("booking_date")),
                sender_name=_safe_str(row.get("sender_name")),
                sender_country=sc,
                receiver_name=_safe_str(row.get("receiver_name")),
                receiver_country=rc,
                description=f"FATF high-risk country '{hr_c}' in EUR {amount:,.2f} {msg} transaction.",
            ))
        return alerts


if __name__ == "__main__":
    print("\nDetectors quick test\n")
    base = datetime(2024, 6, 1, 10, 0, 0)
    rows = [{"transaction_id": f"T{i}", "message_type": "MT103",
             "timestamp": (base + timedelta(hours=i * 8)).isoformat(),
             "booking_date": "2024-06-01", "sender_name": "SHELL CO",
             "sender_country": "DE", "receiver_name": "BANK", "receiver_country": "VG",
             "amount_eur": 9500 + i * 10, "currency": "EUR"} for i in range(5)]
    hits = StructuringDetector().detect(pd.DataFrame(rows))
    print(f"  Structuring: {len(hits)} alerts")

    rows2 = [{"transaction_id": "L1", "message_type": "MT103",
              "timestamp": base.isoformat(), "booking_date": "2024-06-01",
              "sender_name": "FUND", "sender_country": "DE", "receiver_name": "BANK",
              "receiver_country": "LU", "amount_eur": 5_000_000, "currency": "EUR"}]
    hits2 = LargeTransactionDetector().detect(pd.DataFrame(rows2))
    print(f"  Large txn:   {len(hits2)} alerts")
    print()
