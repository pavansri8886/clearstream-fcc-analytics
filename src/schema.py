"""
schema.py
---------
Single source of truth for the alert data model.

Every alert — whether from sanctions screening or AML rule detectors —
produces an AlertRecord. No more mismatched fields between screener
and detectors. One schema, used everywhere.

Fields are designed to satisfy three consumers:
  1. alerts.csv           → pipeline output, queryable
  2. Excel compliance report → Track 2 reports
  3. SAR register / PMO   → Track 3 documents

This file has NO dependencies on any other project file.
It is imported by: screener.py, detectors.py, pipeline.py,
aggregator.py, report_generator.py, pmo_generator.py, sar_generator.py
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import uuid
from datetime import datetime, date


# ── ALL POSSIBLE COLUMNS IN alerts.csv ───────────────────────────────────
# Order matters — this is the exact column order in every output file.

ALERT_COLUMNS = [
    # Identity
    "alert_id",
    "transaction_id",
    "message_type",           # MT103 | MT202 | MT540

    # Classification
    "alert_type",             # SANCTIONS_HIT | STRUCTURING | VELOCITY |
                              # LARGE_TRANSACTION | HIGH_RISK_CORRIDOR
    "alert_severity",         # HIGH | MEDIUM | LOW
    "aml_typology",           # FATF typology label
    "alert_status",           # OPEN | CLOSED | ESCALATED | FALSE_POSITIVE

    # Transaction fields
    "amount_eur",
    "currency",
    "booking_date",
    "month",                  # YYYY-MM  (derived)
    "week_number",            # ISO week number (derived)
    "days_open",              # days since booking_date (derived)

    # Counterparty fields
    "sender_name",
    "sender_country",
    "receiver_name",
    "receiver_country",
    "corridor",               # "DE → IR"  (derived)

    # Clustering
    "cluster_id",             # groups related alerts (structuring clusters etc.)

    # Sanctions-specific (NULL for non-sanctions alerts)
    "matched_field",          # sender_name | receiver_name etc.
    "matched_value",          # exact text found in transaction
    "matched_entity_uid",     # OFAC-7114 | UN-QDe.012 etc.
    "matched_entity_name",    # canonical sanctioned name
    "match_type",             # EXACT | FUZZY
    "match_score",            # 100 for exact, 85-99 for fuzzy
    "list_source",            # OFAC-SDN | UN-CONSOLIDATED | EU-CONSOLIDATED
    "programme",              # IRAN | RUSSIA | DPRK | SDGT etc.
    "sanctions_country",      # ISO-2 country of sanctioned entity

    # SAR fields (NULL unless is_sar_candidate = True)
    "is_sar_candidate",       # True if HIGH severity sanctions hit
    "sar_narrative",          # auto-generated SAR text

    # Description
    "description",            # human-readable alert description
]


# ── ALERT RECORD DATACLASS ────────────────────────────────────────────────

@dataclass
class AlertRecord:
    """
    Unified alert record. Produced by both screener.py and detectors.py.
    Consumed by pipeline.py, aggregator.py, and all report generators.
    """

    # Required fields
    transaction_id: str
    message_type: str
    alert_type: str
    alert_severity: str
    aml_typology: str
    amount_eur: float
    booking_date: str
    sender_name: str
    sender_country: str
    receiver_name: str
    receiver_country: str
    description: str

    # Auto-generated
    alert_id: str = field(default_factory=lambda: f"ALT-{uuid.uuid4().hex[:10].upper()}")
    alert_status: str = "OPEN"

    # Derived fields — populated by pipeline.py after creation
    month: Optional[str] = None
    week_number: Optional[int] = None
    days_open: Optional[int] = None
    corridor: Optional[str] = None
    cluster_id: Optional[str] = None
    currency: Optional[str] = None

    # Sanctions-specific
    matched_field: Optional[str] = None
    matched_value: Optional[str] = None
    matched_entity_uid: Optional[str] = None
    matched_entity_name: Optional[str] = None
    match_type: Optional[str] = None
    match_score: Optional[int] = None
    list_source: Optional[str] = None
    programme: Optional[str] = None
    sanctions_country: Optional[str] = None

    # SAR fields
    is_sar_candidate: bool = False
    sar_narrative: Optional[str] = None

    def enrich_derived_fields(self) -> "AlertRecord":
        """
        Compute all derived fields from existing data.
        Called by pipeline.py after every alert is created.
        """
        # month and week
        try:
            dt = datetime.fromisoformat(self.booking_date)
            self.month = dt.strftime("%Y-%m")
            self.week_number = dt.isocalendar()[1]
            self.days_open = (datetime.today() - dt).days
        except (ValueError, TypeError):
            self.month = None
            self.week_number = None
            self.days_open = None

        # corridor
        sc = (self.sender_country or "").strip().upper()
        rc = (self.receiver_country or "").strip().upper()
        if sc and rc:
            self.corridor = f"{sc} → {rc}"

        # SAR candidate — HIGH severity sanctions hit only
        if (self.alert_type == "SANCTIONS_HIT"
                and self.alert_severity == "HIGH"
                and not self.is_sar_candidate):
            self.is_sar_candidate = True
            self.sar_narrative = _build_sar_narrative(self)

        return self

    def to_dict(self) -> dict:
        """Serialize to dict with exact ALERT_COLUMNS order."""
        d = asdict(self)
        # Return in column order, filling any missing with None
        return {col: d.get(col) for col in ALERT_COLUMNS}


# ── SAR NARRATIVE BUILDER ─────────────────────────────────────────────────

def _build_sar_narrative(alert: AlertRecord) -> str:
    """
    Auto-generate a SAR (Suspicious Activity Report) narrative.
    Format follows CSSF / goAML submission requirements.
    """
    return (
        f"SUSPICIOUS ACTIVITY REPORT — AUTO-GENERATED NARRATIVE\n"
        f"Reporting Entity: Clearstream Banking S.A., Luxembourg\n"
        f"Date of Detection: {alert.booking_date}\n\n"
        f"A transaction ({alert.transaction_id}) of EUR {alert.amount_eur:,.2f} "
        f"was flagged during routine sanctions screening. "
        f"The {'sender' if 'sender' in (alert.matched_field or '') else 'counterparty'} "
        f"'{alert.matched_value}' returned a {alert.match_type} match "
        f"(score: {alert.match_score}/100) against '{alert.matched_entity_name}' "
        f"(UID: {alert.matched_entity_uid}) on the {alert.list_source} "
        f"under the {alert.programme} sanctions programme.\n\n"
        f"The transaction originated from {alert.sender_country} "
        f"and was directed to {alert.receiver_country} "
        f"via a {alert.message_type} instruction.\n\n"
        f"This report is filed pursuant to Luxembourg Law of 12 November 2004 "
        f"on AML/CFT obligations and CSSF Regulation 12-02. "
        f"The transaction has been placed on hold pending investigation."
    )


# ── SEVERITY MAP ──────────────────────────────────────────────────────────

def determine_severity(alert_type: str, amount_eur: float,
                       is_high_risk_country: bool = False) -> str:
    """
    Centralised severity determination.
    Single logic used by both screener and detectors.
    """
    if alert_type == "SANCTIONS_HIT":
        return "HIGH"
    if alert_type == "STRUCTURING":
        return "HIGH"
    if alert_type == "VELOCITY_ABUSE":
        return "HIGH"
    if alert_type == "LARGE_TRANSACTION" and amount_eur >= 5_000_000:
        return "HIGH"
    if alert_type == "LARGE_TRANSACTION":
        return "MEDIUM"
    if alert_type == "HIGH_RISK_CORRIDOR" and is_high_risk_country:
        return "MEDIUM"
    return "LOW"
