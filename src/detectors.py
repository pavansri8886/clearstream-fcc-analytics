"""
detectors.py
------------
AML rule-based detectors. Each detector implements one FATF typology.
All detectors return list[AlertRecord] — same type as screener.py.

Detectors:
  1. StructuringDetector       — sub-threshold splitting (smurfing)
  2. VelocityDetector          — abnormal transaction frequency
  3. LargeTransactionDetector  — single transactions above thresholds
  4. HighRiskCorridorDetector  — FATF grey-list country involvement

Usage (test):
    python src/detectors.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from schema import AlertRecord, determine_severity

FATF_HIGH_RISK = {
    "AF", "KP", "IR", "MM", "SY", "YE", "IQ", "LY",
    "SS", "PK", "NG", "AE", "TR", "VN", "PH", "HT", "JM",
}

def _safe_float(val) -> float:
    try:
        return float(val or 0)
    except (ValueError, TypeError):
        return 0.0

def _safe_str(val) -> str:
    return str(val or "").strip()

def _cluster_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

def _resolve_parties(row, msg_type: str = "") -> tuple[str, str, str, str]:
    mt = _safe_str(row.get("message_type", msg_type)).upper()
    if mt == "MT202":
        return (
            _safe_str(row.get("ordering_institution_name")),
            _safe_str(row.get("ordering_institution_country")),
            _safe_str(row.get("beneficiary_institution_name")),
            _safe_str(row.get("beneficiary_institution_country")),
        )
    if mt in ("MT540","DELIVER_AGAINST_PAYMENT","RECEIVE_AGAINST_PAYMENT",
              "DELIVER_FREE","RECEIVE_FREE"):
        return (
            _safe_str(row.get("delivering_party_name")),
            _safe_str(row.get("delivering_party_country")),
            _safe_str(row.get("receiving_party_name")),
            _safe_str(row.get("receiving_party_country")),
        )
    return (
        _safe_str(row.get("sender_name")),
        _safe_str(row.get("sender_country")),
        _safe_str(row.get("receiver_name")),
        _safe_str(row.get("receiver_country")),
    )


class StructuringDetector:
    """
    Detects structuring (smurfing):
    3+ transactions between EUR 5,000-9,999 from same sender within 72h.
    FATF Typology: deliberate splitting below EUR 10k reporting threshold.
    """
    THRESHOLD_LOW  = 5_000
    THRESHOLD_HIGH = 9_999
    MIN_COUNT      = 3
    WINDOW_HOURS   = 72

    def detect(self, df) -> list[AlertRecord]:
        import pandas as pd
        alerts = []

        # Guard BEFORE any column access — empty df has no columns at all
        if df.empty or "amount_eur" not in df.columns:
            return alerts

        sub = df[
            (df["amount_eur"].apply(_safe_float) >= self.THRESHOLD_LOW) &
            (df["amount_eur"].apply(_safe_float) <= self.THRESHOLD_HIGH)
        ].copy()

        if sub.empty:
            return alerts

        sub["_ts"]     = pd.to_datetime(sub["timestamp"], errors="coerce")
        sub["_amount"] = sub["amount_eur"].apply(_safe_float)
        sub["_sender"] = sub["sender_name"].apply(_safe_str)

        seen_clusters = set()

        for sender, group in sub.groupby("_sender"):
            if len(group) < self.MIN_COUNT:
                continue
            group = group.sort_values("_ts")

            for _, row in group.iterrows():
                window_end = row["_ts"] + timedelta(hours=self.WINDOW_HOURS)
                window = group[
                    (group["_ts"] >= row["_ts"]) &
                    (group["_ts"] <= window_end)
                ]
                if len(window) < self.MIN_COUNT:
                    continue

                cluster_key = f"{sender}_{row['_ts'].date()}"
                if cluster_key in seen_clusters:
                    continue
                seen_clusters.add(cluster_key)

                cid   = _cluster_id("STR")
                total = window["_amount"].sum()

                for _, txn in window.iterrows():
                    sn, sc, rn, rc = _resolve_parties(txn)
                    a = _safe_float(txn.get("amount_eur"))
                    alert = AlertRecord(
                        transaction_id=_safe_str(txn.get("transaction_id")),
                        message_type="MT103",
                        alert_type="STRUCTURING",
                        alert_severity=determine_severity("STRUCTURING", a),
                        aml_typology="STRUCTURING",
                        amount_eur=a,
                        currency=_safe_str(txn.get("currency","EUR")),
                        booking_date=_safe_str(txn.get("booking_date")),
                        sender_name=sn, sender_country=sc,
                        receiver_name=rn, receiver_country=rc,
                        cluster_id=cid,
                        description=(
                            f"Structuring: {len(window)} transactions "
                            f"EUR {self.THRESHOLD_LOW:,}-{self.THRESHOLD_HIGH:,} "
                            f"from '{sender}' in {self.WINDOW_HOURS}h. "
                            f"Total: EUR {total:,.2f}"
                        ),
                    )
                    alerts.append(alert)
                break

        return alerts


class VelocityDetector:
    """
    Detects abnormal transaction velocity.
    20+ transactions from same sender within any 1-hour window.
    """
    MAX_PER_HOUR = 20

    def detect(self, df) -> list[AlertRecord]:
        import pandas as pd
        alerts = []

        if df.empty or "sender_name" not in df.columns:
            return alerts

        df = df.copy()
        df["_ts"]     = pd.to_datetime(df["timestamp"], errors="coerce")
        df["_sender"] = df["sender_name"].apply(_safe_str)
        df["_amount"] = df["amount_eur"].apply(_safe_float) if "amount_eur" in df.columns else 0

        seen = set()

        for sender, group in df.groupby("_sender"):
            if len(group) < self.MAX_PER_HOUR:
                continue
            group = group.sort_values("_ts")

            for _, row in group.iterrows():
                window = group[
                    (group["_ts"] >= row["_ts"]) &
                    (group["_ts"] <= row["_ts"] + timedelta(hours=1))
                ]
                if len(window) < self.MAX_PER_HOUR:
                    continue

                key = f"{sender}_{row['_ts'].strftime('%Y%m%d%H')}"
                if key in seen:
                    continue
                seen.add(key)

                cid   = _cluster_id("VEL")
                total = window["_amount"].sum()

                for _, txn in window.head(5).iterrows():
                    sn, sc, rn, rc = _resolve_parties(txn)
                    a = _safe_float(txn.get("amount_eur"))
                    alert = AlertRecord(
                        transaction_id=_safe_str(txn.get("transaction_id")),
                        message_type=_safe_str(txn.get("message_type","MT103")),
                        alert_type="VELOCITY_ABUSE",
                        alert_severity=determine_severity("VELOCITY_ABUSE", a),
                        aml_typology="VELOCITY_ABUSE",
                        amount_eur=a,
                        currency=_safe_str(txn.get("currency","EUR")),
                        booking_date=_safe_str(txn.get("booking_date")),
                        sender_name=sn, sender_country=sc,
                        receiver_name=rn, receiver_country=rc,
                        cluster_id=cid,
                        description=(
                            f"Velocity: '{sender}' sent {len(window)} transactions "
                            f"in 1 hour (threshold: {self.MAX_PER_HOUR}). "
                            f"Total: EUR {total:,.2f}"
                        ),
                    )
                    alerts.append(alert)
                break

        return alerts


class LargeTransactionDetector:
    """
    Flags single large transactions.
    >= EUR 1M -> HIGH severity.
    >= EUR 100k involving FATF high-risk country -> MEDIUM severity.
    """
    LARGE     = 1_000_000
    HIGH_RISK = 100_000

    def detect(self, df) -> list[AlertRecord]:
        alerts = []

        if df.empty:
            return alerts

        for _, row in df.iterrows():
            amount = _safe_float(row.get("amount_eur") or row.get("settlement_amount_eur"))
            msg    = _safe_str(row.get("message_type","MT103"))
            sn, sc, rn, rc = _resolve_parties(row, msg)
            is_hr  = sc in FATF_HIGH_RISK or rc in FATF_HIGH_RISK
            hr_c   = sc if sc in FATF_HIGH_RISK else (rc if rc in FATF_HIGH_RISK else "")
            bdate  = _safe_str(row.get("booking_date") or row.get("trade_date",""))

            if amount >= self.LARGE:
                alerts.append(AlertRecord(
                    transaction_id=_safe_str(row.get("transaction_id")),
                    message_type=msg,
                    alert_type="LARGE_TRANSACTION",
                    alert_severity=determine_severity("LARGE_TRANSACTION", amount),
                    aml_typology="LARGE_TRANSACTION",
                    amount_eur=amount,
                    currency=_safe_str(row.get("currency","EUR")),
                    booking_date=bdate,
                    sender_name=sn, sender_country=sc,
                    receiver_name=rn, receiver_country=rc,
                    description=(
                        f"Large transaction: EUR {amount:,.2f} exceeds "
                        f"EUR {self.LARGE:,} reporting threshold."
                    ),
                ))
            elif amount >= self.HIGH_RISK and is_hr:
                alerts.append(AlertRecord(
                    transaction_id=_safe_str(row.get("transaction_id")),
                    message_type=msg,
                    alert_type="HIGH_RISK_CORRIDOR",
                    alert_severity="MEDIUM",
                    aml_typology="HIGH_RISK_JURISDICTION",
                    amount_eur=amount,
                    currency=_safe_str(row.get("currency","EUR")),
                    booking_date=bdate,
                    sender_name=sn, sender_country=sc,
                    receiver_name=rn, receiver_country=rc,
                    description=(
                        f"High-risk corridor: EUR {amount:,.2f} involving "
                        f"FATF jurisdiction '{hr_c}'."
                    ),
                ))
        return alerts


class HighRiskCorridorDetector:
    """
    Flags any transaction involving a FATF grey-list country.
    """

    def detect(self, df) -> list[AlertRecord]:
        alerts = []

        if df.empty:
            return alerts

        for _, row in df.iterrows():
            msg    = _safe_str(row.get("message_type","MT103"))
            sn, sc, rn, rc = _resolve_parties(row, msg)
            amount = _safe_float(row.get("amount_eur") or row.get("settlement_amount_eur",0))
            bdate  = _safe_str(row.get("booking_date") or row.get("trade_date",""))
            hr_c   = sc if sc in FATF_HIGH_RISK else (rc if rc in FATF_HIGH_RISK else None)

            if not hr_c:
                continue

            alerts.append(AlertRecord(
                transaction_id=_safe_str(row.get("transaction_id")),
                message_type=msg,
                alert_type="HIGH_RISK_CORRIDOR",
                alert_severity="MEDIUM",
                aml_typology="HIGH_RISK_JURISDICTION",
                amount_eur=amount,
                currency=_safe_str(row.get("currency","EUR")),
                booking_date=bdate,
                sender_name=sn, sender_country=sc,
                receiver_name=rn, receiver_country=rc,
                description=(
                    f"FATF high-risk jurisdiction '{hr_c}' in "
                    f"EUR {amount:,.2f} {msg} transaction."
                ),
            ))
        return alerts


if __name__ == "__main__":
    try:
        import pandas as pd
    except ImportError:
        print("pip install pandas"); raise SystemExit(1)

    print("\nDetectors quick test\n")
    base = datetime(2024,6,1,10,0,0)
    rows = [{"transaction_id":f"T{i}","message_type":"MT103",
             "timestamp":(base+timedelta(hours=i*8)).isoformat(),
             "booking_date":"2024-06-01","sender_name":"SHELL CO",
             "sender_country":"DE","receiver_name":"BANK","receiver_country":"VG",
             "amount_eur":9500+i*10,"currency":"EUR"} for i in range(5)]
    hits = StructuringDetector().detect(pd.DataFrame(rows))
    print(f"  Structuring: {len(hits)} alerts")

    rows2 = [{"transaction_id":"L1","message_type":"MT103",
              "timestamp":base.isoformat(),"booking_date":"2024-06-01",
              "sender_name":"FUND","sender_country":"DE","receiver_name":"BANK",
              "receiver_country":"LU","amount_eur":5_000_000,"currency":"EUR"}]
    hits2 = LargeTransactionDetector().detect(pd.DataFrame(rows2))
    print(f"  Large txn:   {len(hits2)} alerts")
    print()
