"""
aggregator.py
-------------
Reads alerts.csv and computes all KPIs needed by downstream reports.
Writes clean summary CSVs to data/processed/summary/.

This is the separation layer between raw pipeline output and reports.
report_generator.py, pmo_generator.py, and sar_generator.py all read
from summary/ — never from raw alerts.csv directly.

Outputs:
  summary/kpis.csv              — headline metrics (for exec summary cards)
  summary/monthly_trends.csv    — alert counts by month and type
  summary/country_exposure.csv  — top corridors and countries by alert volume
  summary/top_alerts.csv        — top 100 highest-value open alerts
  summary/sar_candidates.csv    — all SAR-candidate sanctions hits
  summary/alert_type_breakdown.csv — counts and % by alert type

Usage:
    python src/aggregator.py
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict, Counter
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

ALERTS_PATH  = ROOT / "data" / "processed" / "alerts.csv"
SUMMARY_PATH = ROOT / "data" / "processed" / "summary_stats.csv"
OUTPUT_DIR   = ROOT / "data" / "processed" / "summary"


def _safe_float(val) -> float:
    try:
        return float(val or 0)
    except (ValueError, TypeError):
        return 0.0

def _safe_int(val) -> int:
    try:
        return int(float(val or 0))
    except (ValueError, TypeError):
        return 0

def _safe_str(val) -> str:
    return str(val or "").strip()


def run_aggregation() -> None:
    print("\n📐 Aggregator — Computing KPIs...\n")

    if not ALERTS_PATH.exists():
        print(f"  ✗ alerts.csv not found: {ALERTS_PATH}")
        print("    Run pipeline first: python src/pipeline.py")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load alerts.csv ───────────────────────────────────────────────────
    alerts = []
    with open(ALERTS_PATH, newline="", encoding="utf-8") as f:
        alerts = list(csv.DictReader(f))

    print(f"  Loaded {len(alerts):,} alerts from alerts.csv")

    # Load pipeline summary stats
    pipeline_stats = {}
    if SUMMARY_PATH.exists():
        with open(SUMMARY_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pipeline_stats[row["metric"]] = row["value"]

    # ── 1. KPIs CSV ───────────────────────────────────────────────────────
    total_alerts   = len(alerts)
    high_sev       = sum(1 for a in alerts if _safe_str(a.get("alert_severity")) == "HIGH")
    medium_sev     = sum(1 for a in alerts if _safe_str(a.get("alert_severity")) == "MEDIUM")
    sanctions      = sum(1 for a in alerts if _safe_str(a.get("alert_type")) == "SANCTIONS_HIT")
    structuring    = sum(1 for a in alerts if _safe_str(a.get("alert_type")) == "STRUCTURING")
    velocity       = sum(1 for a in alerts if _safe_str(a.get("alert_type")) == "VELOCITY_ABUSE")
    large_txn      = sum(1 for a in alerts if _safe_str(a.get("alert_type")) == "LARGE_TRANSACTION")
    high_risk      = sum(1 for a in alerts if _safe_str(a.get("alert_type")) == "HIGH_RISK_CORRIDOR")
    sar_candidates = sum(1 for a in alerts if _safe_str(a.get("is_sar_candidate")).lower() == "true")
    total_exposure = sum(_safe_float(a.get("amount_eur")) for a in alerts
                         if _safe_str(a.get("alert_severity")) == "HIGH")
    rows_processed = _safe_int(pipeline_stats.get("Total Rows Processed", 0))
    alert_rate     = round(total_alerts / max(rows_processed, 1) * 100, 2)

    kpis = [
        {"metric": "Total Rows Screened",        "value": rows_processed,   "format": "number"},
        {"metric": "Total Alerts",               "value": total_alerts,     "format": "number"},
        {"metric": "Alert Rate (%)",             "value": alert_rate,       "format": "percent"},
        {"metric": "HIGH Severity",              "value": high_sev,         "format": "number"},
        {"metric": "MEDIUM Severity",            "value": medium_sev,       "format": "number"},
        {"metric": "Sanctions Hits",             "value": sanctions,        "format": "number"},
        {"metric": "Structuring Cases",          "value": structuring,      "format": "number"},
        {"metric": "Velocity Alerts",            "value": velocity,         "format": "number"},
        {"metric": "Large Transaction Alerts",   "value": large_txn,        "format": "number"},
        {"metric": "High-Risk Corridor Alerts",  "value": high_risk,        "format": "number"},
        {"metric": "SAR Candidates",             "value": sar_candidates,   "format": "number"},
        {"metric": "Total HIGH Exposure (EUR)",  "value": round(total_exposure, 2), "format": "currency"},
    ]

    _write_csv(kpis, OUTPUT_DIR / "kpis.csv",
               ["metric", "value", "format"])
    print(f"  ✓ kpis.csv ({len(kpis)} metrics)")

    # ── 2. Monthly trends ─────────────────────────────────────────────────
    monthly: dict[str, Counter] = defaultdict(Counter)
    for a in alerts:
        month = _safe_str(a.get("month", ""))[:7]   # YYYY-MM
        if not month:
            continue
        monthly[month][_safe_str(a.get("alert_type"))] += 1

    alert_types_seen = sorted({t for m in monthly.values() for t in m})
    trend_rows = []
    for month in sorted(monthly.keys()):
        row = {"month": month, "total": sum(monthly[month].values())}
        for at in alert_types_seen:
            row[at] = monthly[month].get(at, 0)
        trend_rows.append(row)

    trend_cols = ["month", "total"] + alert_types_seen
    _write_csv(trend_rows, OUTPUT_DIR / "monthly_trends.csv", trend_cols)
    print(f"  ✓ monthly_trends.csv ({len(trend_rows)} months)")

    # ── 3. Country exposure ───────────────────────────────────────────────
    corridor_counts: Counter = Counter()
    corridor_exposure: dict[str, float] = defaultdict(float)
    country_counts: Counter = Counter()

    for a in alerts:
        corridor = _safe_str(a.get("corridor"))
        sc = _safe_str(a.get("sender_country"))
        rc = _safe_str(a.get("receiver_country"))
        amt = _safe_float(a.get("amount_eur"))

        if corridor:
            corridor_counts[corridor] += 1
            corridor_exposure[corridor] += amt
        if sc:
            country_counts[sc] += 1
        if rc:
            country_counts[rc] += 1

    country_rows = [
        {
            "corridor": corridor,
            "alert_count": corridor_counts[corridor],
            "total_exposure_eur": round(corridor_exposure[corridor], 2),
        }
        for corridor in sorted(corridor_counts, key=lambda x: -corridor_counts[x])
    ][:50]   # top 50

    _write_csv(country_rows, OUTPUT_DIR / "country_exposure.csv",
               ["corridor", "alert_count", "total_exposure_eur"])
    print(f"  ✓ country_exposure.csv ({len(country_rows)} corridors)")

    # ── 4. Top alerts (highest value, open, HIGH severity) ────────────────
    high_open = [
        a for a in alerts
        if _safe_str(a.get("alert_severity")) == "HIGH"
        and _safe_str(a.get("alert_status")) == "OPEN"
    ]
    high_open.sort(key=lambda a: _safe_float(a.get("amount_eur")), reverse=True)

    top_fields = [
        "alert_id", "transaction_id", "message_type",
        "alert_type", "alert_severity", "aml_typology",
        "amount_eur", "booking_date", "month",
        "sender_name", "sender_country",
        "receiver_name", "receiver_country",
        "corridor", "description",
        "matched_entity_name", "list_source", "programme",
    ]
    _write_csv(high_open[:100], OUTPUT_DIR / "top_alerts.csv", top_fields)
    print(f"  ✓ top_alerts.csv ({min(100, len(high_open))} highest-value HIGH alerts)")

    # ── 5. SAR candidates ─────────────────────────────────────────────────
    sar_rows = [
        a for a in alerts
        if _safe_str(a.get("is_sar_candidate")).lower() == "true"
    ]
    sar_fields = [
        "alert_id", "transaction_id", "message_type",
        "alert_severity", "amount_eur", "booking_date",
        "sender_name", "sender_country",
        "receiver_name", "receiver_country",
        "matched_field", "matched_value",
        "matched_entity_uid", "matched_entity_name",
        "match_type", "match_score",
        "list_source", "programme", "sanctions_country",
        "sar_narrative", "alert_status",
    ]
    _write_csv(sar_rows, OUTPUT_DIR / "sar_candidates.csv", sar_fields)
    print(f"  ✓ sar_candidates.csv ({len(sar_rows)} SAR candidates)")

    # ── 6. Alert type breakdown ───────────────────────────────────────────
    type_counts = Counter(_safe_str(a.get("alert_type")) for a in alerts)
    breakdown = [
        {
            "alert_type":       at,
            "count":            type_counts[at],
            "pct_of_total":     round(type_counts[at] / max(total_alerts, 1) * 100, 1),
            "severity":         _type_severity(at),
            "fatf_typology":    _type_fatf(at),
        }
        for at in sorted(type_counts, key=lambda x: -type_counts[x])
    ]
    _write_csv(breakdown, OUTPUT_DIR / "alert_type_breakdown.csv",
               ["alert_type", "count", "pct_of_total", "severity", "fatf_typology"])
    print(f"  ✓ alert_type_breakdown.csv ({len(breakdown)} types)")

    print(f"\n✅ Aggregation complete → {OUTPUT_DIR}\n")
    return {
        "kpis": kpis,
        "trend_rows": trend_rows,
        "country_rows": country_rows,
        "top_alerts": high_open[:100],
        "sar_rows": sar_rows,
        "breakdown": breakdown,
    }


def _write_csv(rows: list[dict], path: Path, fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _type_severity(alert_type: str) -> str:
    return {
        "SANCTIONS_HIT":      "HIGH",
        "STRUCTURING":        "HIGH",
        "VELOCITY_ABUSE":     "HIGH",
        "LARGE_TRANSACTION":  "MEDIUM–HIGH",
        "HIGH_RISK_CORRIDOR": "MEDIUM",
    }.get(alert_type, "LOW")


def _type_fatf(alert_type: str) -> str:
    return {
        "SANCTIONS_HIT":      "Sanctions Evasion",
        "STRUCTURING":        "Structuring / Smurfing",
        "VELOCITY_ABUSE":     "Rapid Movement of Funds",
        "LARGE_TRANSACTION":  "Large Cash Transactions",
        "HIGH_RISK_CORRIDOR": "High-Risk Jurisdiction",
    }.get(alert_type, "—")


if __name__ == "__main__":
    run_aggregation()
