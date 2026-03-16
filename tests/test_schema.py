"""
tests/test_schema.py
--------------------
Unit tests for schema.py — the unified AlertRecord data model.

Tests cover:
  - AlertRecord creation with required fields
  - Derived field computation (month, week_number, corridor, days_open)
  - SAR candidate auto-flagging and narrative generation
  - to_dict() produces exact ALERT_COLUMNS order
  - determine_severity() logic for all alert types
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from schema import AlertRecord, ALERT_COLUMNS, determine_severity


def _make_alert(**kwargs) -> AlertRecord:
    """Build a minimal valid AlertRecord with safe defaults."""
    defaults = dict(
        transaction_id="TXN-TEST-001",
        message_type="MT103",
        alert_type="LARGE_TRANSACTION",
        alert_severity="HIGH",
        aml_typology="LARGE_TRANSACTION",
        amount_eur=1_500_000.0,
        booking_date="2024-06-15",
        sender_name="TEST SENDER BANK",
        sender_country="DE",
        receiver_name="TEST RECEIVER BANK",
        receiver_country="LU",
        description="Test alert description",
    )
    defaults.update(kwargs)
    return AlertRecord(**defaults)


class TestAlertRecordCreation(unittest.TestCase):

    def test_creates_with_required_fields(self):
        alert = _make_alert()
        self.assertEqual(alert.transaction_id, "TXN-TEST-001")
        self.assertEqual(alert.message_type, "MT103")
        self.assertEqual(alert.alert_type, "LARGE_TRANSACTION")
        self.assertEqual(alert.amount_eur, 1_500_000.0)

    def test_alert_id_auto_generated(self):
        alert = _make_alert()
        self.assertTrue(alert.alert_id.startswith("ALT-"))
        self.assertEqual(len(alert.alert_id), 14)  # ALT- + 10 hex chars

    def test_alert_id_unique_per_instance(self):
        a1 = _make_alert()
        a2 = _make_alert()
        self.assertNotEqual(a1.alert_id, a2.alert_id)

    def test_default_status_is_open(self):
        alert = _make_alert()
        self.assertEqual(alert.alert_status, "OPEN")

    def test_optional_fields_default_none(self):
        alert = _make_alert()
        self.assertIsNone(alert.month)
        self.assertIsNone(alert.corridor)
        self.assertIsNone(alert.cluster_id)
        self.assertIsNone(alert.matched_entity_uid)
        self.assertIsNone(alert.sar_narrative)

    def test_is_sar_candidate_defaults_false(self):
        alert = _make_alert()
        self.assertFalse(alert.is_sar_candidate)


class TestDerivedFields(unittest.TestCase):

    def test_month_derived_correctly(self):
        alert = _make_alert(booking_date="2024-06-15")
        alert.enrich_derived_fields()
        self.assertEqual(alert.month, "2024-06")

    def test_week_number_derived(self):
        alert = _make_alert(booking_date="2024-01-08")
        alert.enrich_derived_fields()
        self.assertEqual(alert.week_number, 2)

    def test_days_open_is_positive(self):
        alert = _make_alert(booking_date="2024-01-01")
        alert.enrich_derived_fields()
        self.assertIsNotNone(alert.days_open)
        self.assertGreater(alert.days_open, 0)

    def test_corridor_derived_correctly(self):
        alert = _make_alert(sender_country="DE", receiver_country="IR")
        alert.enrich_derived_fields()
        self.assertEqual(alert.corridor, "DE → IR")

    def test_corridor_uppercase(self):
        alert = _make_alert(sender_country="de", receiver_country="lu")
        alert.enrich_derived_fields()
        self.assertEqual(alert.corridor, "DE → LU")

    def test_invalid_date_does_not_crash(self):
        alert = _make_alert(booking_date="NOT-A-DATE")
        alert.enrich_derived_fields()
        self.assertIsNone(alert.month)
        self.assertIsNone(alert.week_number)

    def test_empty_date_does_not_crash(self):
        alert = _make_alert(booking_date="")
        alert.enrich_derived_fields()
        self.assertIsNone(alert.month)

    def test_enrich_returns_self(self):
        alert = _make_alert()
        result = alert.enrich_derived_fields()
        self.assertIs(result, alert)


class TestSARCandidate(unittest.TestCase):

    def test_high_severity_sanctions_hit_becomes_sar_candidate(self):
        alert = _make_alert(
            alert_type="SANCTIONS_HIT",
            alert_severity="HIGH",
            matched_value="BANK MELLI IRAN",
            matched_entity_name="BANK MELLI IRAN",
            matched_entity_uid="OFAC-7114",
            match_type="EXACT",
            match_score=100,
            list_source="OFAC-SDN",
            programme="IRAN",
            sanctions_country="IR",
        )
        alert.enrich_derived_fields()
        self.assertTrue(alert.is_sar_candidate)
        self.assertIsNotNone(alert.sar_narrative)

    def test_sar_narrative_contains_key_fields(self):
        alert = _make_alert(
            alert_type="SANCTIONS_HIT",
            alert_severity="HIGH",
            matched_value="GAZPROMBANK",
            matched_entity_name="GAZPROMBANK",
            matched_entity_uid="OFAC-31003",
            match_type="EXACT",
            match_score=100,
            list_source="OFAC-SDN",
            programme="RUSSIA",
            sanctions_country="RU",
        )
        alert.enrich_derived_fields()
        self.assertIn("GAZPROMBANK", alert.sar_narrative)
        self.assertIn("OFAC-SDN", alert.sar_narrative)
        self.assertIn("RUSSIA", alert.sar_narrative)
        self.assertIn("Clearstream Banking S.A.", alert.sar_narrative)

    def test_non_sanctions_alert_not_sar_candidate(self):
        alert = _make_alert(alert_type="STRUCTURING", alert_severity="HIGH")
        alert.enrich_derived_fields()
        self.assertFalse(alert.is_sar_candidate)

    def test_medium_severity_sanctions_not_auto_sar(self):
        alert = _make_alert(
            alert_type="SANCTIONS_HIT",
            alert_severity="MEDIUM",
        )
        alert.enrich_derived_fields()
        self.assertFalse(alert.is_sar_candidate)


class TestToDict(unittest.TestCase):

    def test_to_dict_has_all_columns(self):
        alert = _make_alert()
        d = alert.to_dict()
        for col in ALERT_COLUMNS:
            self.assertIn(col, d, f"Missing column: {col}")

    def test_to_dict_column_order_matches_schema(self):
        alert = _make_alert()
        d = alert.to_dict()
        keys = list(d.keys())
        self.assertEqual(keys, ALERT_COLUMNS)

    def test_to_dict_values_correct(self):
        alert = _make_alert(
            transaction_id="TXN-999",
            amount_eur=5_000_000.0,
            sender_country="DE",
            receiver_country="RU",
        )
        d = alert.to_dict()
        self.assertEqual(d["transaction_id"], "TXN-999")
        self.assertEqual(d["amount_eur"], 5_000_000.0)

    def test_to_dict_none_for_missing_optional(self):
        alert = _make_alert()
        d = alert.to_dict()
        self.assertIsNone(d["matched_entity_uid"])
        self.assertIsNone(d["sar_narrative"])
        self.assertIsNone(d["cluster_id"])


class TestDetermineSeverity(unittest.TestCase):

    def test_sanctions_hit_always_high(self):
        self.assertEqual(determine_severity("SANCTIONS_HIT", 100), "HIGH")
        self.assertEqual(determine_severity("SANCTIONS_HIT", 1), "HIGH")

    def test_structuring_always_high(self):
        self.assertEqual(determine_severity("STRUCTURING", 9000), "HIGH")

    def test_velocity_always_high(self):
        self.assertEqual(determine_severity("VELOCITY_ABUSE", 50000), "HIGH")

    def test_large_txn_high_above_5m(self):
        self.assertEqual(determine_severity("LARGE_TRANSACTION", 5_000_001), "HIGH")

    def test_large_txn_medium_below_5m(self):
        self.assertEqual(determine_severity("LARGE_TRANSACTION", 1_000_000), "MEDIUM")

    def test_high_risk_corridor_medium(self):
        self.assertEqual(
            determine_severity("HIGH_RISK_CORRIDOR", 200_000, True), "MEDIUM"
        )

    def test_unknown_type_returns_low(self):
        self.assertEqual(determine_severity("UNKNOWN_TYPE", 0), "LOW")


if __name__ == "__main__":
    unittest.main(verbosity=2)
