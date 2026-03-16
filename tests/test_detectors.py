"""
tests/test_detectors.py
-----------------------
Unit tests for detectors.py — AML rule-based detectors.
"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from schema import AlertRecord

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

from detectors import (
    StructuringDetector,
    VelocityDetector,
    LargeTransactionDetector,
    HighRiskCorridorDetector,
)


def _make_df(rows):
    import pandas as pd
    return pd.DataFrame(rows)


def _wire_row(sender="CLEAN CORP", sender_country="DE",
              receiver="BANK INTL", receiver_country="LU",
              amount=50000, hours_offset=0, base_ts=None) -> dict:
    if base_ts is None:
        base_ts = datetime(2024, 6, 1, 10, 0, 0)
    ts = base_ts + timedelta(hours=hours_offset)
    return {
        "transaction_id": f"T-{hours_offset}-{amount}",
        "message_type": "MT103",
        "timestamp": ts.isoformat(),
        "booking_date": ts.date().isoformat(),
        "sender_name": sender,
        "sender_country": sender_country,
        "receiver_name": receiver,
        "receiver_country": receiver_country,
        "amount_eur": str(amount),
        "currency": "EUR",
    }


@unittest.skipUnless(HAS_PANDAS, "pandas not installed")
class TestStructuringDetector(unittest.TestCase):

    def setUp(self):
        self.detector = StructuringDetector()
        self.base = datetime(2024, 6, 1, 10, 0, 0)

    def _structuring_rows(self, n=5, amount=9500, sender="SHELL CO LTD",
                          gap_hours=8):
        return [
            _wire_row(sender=sender, amount=amount,
                      hours_offset=i * gap_hours, base_ts=self.base)
            for i in range(n)
        ]

    def test_detects_5_structuring_transactions(self):
        rows = self._structuring_rows(n=5, gap_hours=8)
        alerts = self.detector.detect(_make_df(rows))
        self.assertGreater(len(alerts), 0)

    def test_detects_minimum_3_transactions(self):
        rows = self._structuring_rows(n=3, gap_hours=8)
        alerts = self.detector.detect(_make_df(rows))
        self.assertGreater(len(alerts), 0)

    def test_does_not_fire_on_2_transactions(self):
        rows = self._structuring_rows(n=2, gap_hours=8)
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 0)

    def test_does_not_fire_on_large_amounts(self):
        rows = self._structuring_rows(n=5, amount=15000)
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 0)

    def test_does_not_fire_on_small_amounts_below_floor(self):
        rows = self._structuring_rows(n=5, amount=2000)
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 0)

    def test_cluster_id_assigned(self):
        rows = self._structuring_rows(n=5)
        alerts = self.detector.detect(_make_df(rows))
        self.assertGreater(len(alerts), 0)
        for alert in alerts:
            self.assertIsNotNone(alert.cluster_id)
            self.assertTrue(alert.cluster_id.startswith("STR-"))

    def test_all_alerts_same_cluster_id(self):
        rows = self._structuring_rows(n=5)
        alerts = self.detector.detect(_make_df(rows))
        self.assertGreater(len(alerts), 0)
        cluster_ids = {a.cluster_id for a in alerts}
        self.assertEqual(len(cluster_ids), 1)

    def test_returns_alert_records(self):
        rows = self._structuring_rows(n=5)
        alerts = self.detector.detect(_make_df(rows))
        for alert in alerts:
            self.assertIsInstance(alert, AlertRecord)

    def test_alert_type_is_structuring(self):
        rows = self._structuring_rows(n=5)
        alerts = self.detector.detect(_make_df(rows))
        for alert in alerts:
            self.assertEqual(alert.alert_type, "STRUCTURING")
            self.assertEqual(alert.alert_severity, "HIGH")

    def test_different_senders_separate_clusters(self):
        rows_a = self._structuring_rows(n=4, sender="COMPANY A")
        rows_b = self._structuring_rows(n=4, sender="COMPANY B")
        alerts = self.detector.detect(_make_df(rows_a + rows_b))
        self.assertGreater(len(alerts), 0)

    def test_empty_dataframe_returns_empty(self):
        """Empty DataFrame must not crash — guard must be before column access."""
        import pandas as pd
        df = pd.DataFrame()
        alerts = self.detector.detect(df)
        self.assertEqual(alerts, [])

    def test_outside_window_not_flagged(self):
        """
        Transactions with 40h gaps: 0h, 40h, 80h, 120h, 160h.
        No 3 consecutive transactions fall within the 72h window,
        so structuring should NOT be detected.
        """
        rows = self._structuring_rows(n=5, gap_hours=40)
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 0)


@unittest.skipUnless(HAS_PANDAS, "pandas not installed")
class TestVelocityDetector(unittest.TestCase):

    def setUp(self):
        self.detector = VelocityDetector()
        self.base = datetime(2024, 6, 1, 10, 0, 0)

    def _velocity_rows(self, n=25, sender="FAST SENDER"):
        return [
            _wire_row(sender=sender, amount=10000,
                      hours_offset=i * 0.02, base_ts=self.base)
            for i in range(n)
        ]

    def test_detects_20_transactions_in_1_hour(self):
        rows = self._velocity_rows(n=25)
        alerts = self.detector.detect(_make_df(rows))
        self.assertGreater(len(alerts), 0)

    def test_does_not_fire_below_threshold(self):
        rows = self._velocity_rows(n=15)
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 0)

    def test_alert_type_is_velocity(self):
        rows = self._velocity_rows(n=25)
        alerts = self.detector.detect(_make_df(rows))
        self.assertGreater(len(alerts), 0)
        for alert in alerts:
            self.assertEqual(alert.alert_type, "VELOCITY_ABUSE")
            self.assertEqual(alert.alert_severity, "HIGH")

    def test_returns_alert_records(self):
        rows = self._velocity_rows(n=25)
        alerts = self.detector.detect(_make_df(rows))
        for alert in alerts:
            self.assertIsInstance(alert, AlertRecord)

    def test_cluster_id_assigned(self):
        rows = self._velocity_rows(n=25)
        alerts = self.detector.detect(_make_df(rows))
        self.assertGreater(len(alerts), 0)
        for alert in alerts:
            self.assertIsNotNone(alert.cluster_id)
            self.assertTrue(alert.cluster_id.startswith("VEL-"))

    def test_empty_dataframe_returns_empty(self):
        import pandas as pd
        alerts = self.detector.detect(pd.DataFrame())
        self.assertEqual(alerts, [])


@unittest.skipUnless(HAS_PANDAS, "pandas not installed")
class TestLargeTransactionDetector(unittest.TestCase):

    def setUp(self):
        self.detector = LargeTransactionDetector()

    def test_large_transaction_flagged_high(self):
        rows = [_wire_row(amount=5_000_000)]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type, "LARGE_TRANSACTION")
        self.assertEqual(alerts[0].alert_severity, "HIGH")

    def test_exactly_1m_flagged(self):
        rows = [_wire_row(amount=1_000_000)]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 1)

    def test_high_risk_country_medium_threshold(self):
        rows = [_wire_row(sender_country="IR", amount=150_000)]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type, "HIGH_RISK_CORRIDOR")
        self.assertEqual(alerts[0].alert_severity, "MEDIUM")

    def test_high_risk_receiver_flagged(self):
        rows = [_wire_row(receiver_country="KP", amount=200_000)]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 1)

    def test_small_clean_transaction_not_flagged(self):
        rows = [_wire_row(amount=50_000)]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 0)

    def test_below_100k_high_risk_not_flagged(self):
        """Below EUR 100k even high-risk country should not trigger this detector"""
        rows = [_wire_row(sender_country="IR", amount=50_000)]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 0)

    def test_returns_alert_records(self):
        rows = [_wire_row(amount=2_000_000)]
        alerts = self.detector.detect(_make_df(rows))
        for alert in alerts:
            self.assertIsInstance(alert, AlertRecord)

    def test_amount_preserved_in_alert(self):
        rows = [_wire_row(amount=7_500_000)]
        alerts = self.detector.detect(_make_df(rows))
        self.assertGreater(len(alerts), 0)
        self.assertAlmostEqual(alerts[0].amount_eur, 7_500_000.0)

    def test_empty_dataframe_returns_empty(self):
        import pandas as pd
        alerts = self.detector.detect(pd.DataFrame())
        self.assertEqual(alerts, [])


@unittest.skipUnless(HAS_PANDAS, "pandas not installed")
class TestHighRiskCorridorDetector(unittest.TestCase):

    def setUp(self):
        self.detector = HighRiskCorridorDetector()

    def test_iran_sender_flagged(self):
        rows = [_wire_row(sender_country="IR", amount=50_000)]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type, "HIGH_RISK_CORRIDOR")

    def test_north_korea_receiver_flagged(self):
        rows = [_wire_row(receiver_country="KP", amount=10_000)]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 1)

    def test_syria_flagged(self):
        rows = [_wire_row(sender_country="SY")]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 1)

    def test_myanmar_flagged(self):
        rows = [_wire_row(sender_country="MM")]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 1)

    def test_clean_eu_corridor_not_flagged(self):
        rows = [_wire_row(sender_country="DE", receiver_country="LU")]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 0)

    def test_us_uk_not_flagged(self):
        rows = [_wire_row(sender_country="US", receiver_country="GB")]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 0)

    def test_severity_is_medium(self):
        rows = [_wire_row(sender_country="IR")]
        alerts = self.detector.detect(_make_df(rows))
        self.assertGreater(len(alerts), 0)
        self.assertEqual(alerts[0].alert_severity, "MEDIUM")

    def test_multiple_high_risk_rows(self):
        rows = [
            _wire_row(sender_country="IR"),
            _wire_row(sender_country="DE"),   # clean
            _wire_row(sender_country="KP"),
            _wire_row(sender_country="LU"),   # clean
            _wire_row(sender_country="AF"),
        ]
        alerts = self.detector.detect(_make_df(rows))
        self.assertEqual(len(alerts), 3)

    def test_returns_alert_records(self):
        rows = [_wire_row(sender_country="SY")]
        alerts = self.detector.detect(_make_df(rows))
        for alert in alerts:
            self.assertIsInstance(alert, AlertRecord)

    def test_empty_dataframe_returns_empty(self):
        import pandas as pd
        alerts = self.detector.detect(pd.DataFrame())
        self.assertEqual(alerts, [])

    def test_description_contains_country_code(self):
        rows = [_wire_row(sender_country="IR")]
        alerts = self.detector.detect(_make_df(rows))
        self.assertGreater(len(alerts), 0)
        self.assertIn("IR", alerts[0].description)


if __name__ == "__main__":
    unittest.main(verbosity=2)
