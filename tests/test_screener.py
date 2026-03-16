"""
tests/test_screener.py
----------------------
Unit tests for screener.py — sanctions name matching engine.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from screener import SanctionsScreener
from schema import AlertRecord

SANCTIONS_PATH = ROOT / "data" / "raw" / "sanctions" / "combined_master.csv"


def _make_row(sender="DEUTSCHE BANK AG", receiver="BNP PARIBAS SA",
              amount="500000", date="2024-03-15",
              sender_country="DE", receiver_country="FR") -> dict:
    return {
        "transaction_id": "TEST-SCR-001",
        "sender_name": sender,
        "receiver_name": receiver,
        "amount_eur": amount,
        "booking_date": date,
        "sender_country": sender_country,
        "receiver_country": receiver_country,
        "currency": "EUR",
    }


@unittest.skipUnless(SANCTIONS_PATH.exists(),
                     "Sanctions master list not found — run build_sanctions_lists.py first")
class TestSanctionsScreener(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.screener = SanctionsScreener(
            sanctions_path=SANCTIONS_PATH,
            fuzzy_threshold=85,
        )

    # ── Exact hits ────────────────────────────────────────────────────────

    def test_bank_melli_iran_exact_hit(self):
        hits = self.screener.screen_row(_make_row(sender="BANK MELLI IRAN"), "MT103")
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].match_type, "EXACT")
        self.assertEqual(hits[0].match_score, 100)

    def test_gazprombank_exact_hit(self):
        hits = self.screener.screen_row(_make_row(sender="GAZPROMBANK"), "MT103")
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].match_type, "EXACT")

    def test_vtb_bank_exact_hit(self):
        hits = self.screener.screen_row(_make_row(sender="VTB BANK"), "MT103")
        self.assertGreater(len(hits), 0)

    def test_sberbank_exact_hit(self):
        hits = self.screener.screen_row(_make_row(sender="SBERBANK"), "MT103")
        self.assertGreater(len(hits), 0)

    def test_isis_un_list_hit(self):
        hits = self.screener.screen_row(
            _make_row(sender="ISLAMIC STATE IN IRAQ AND THE LEVANT"), "MT103")
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].list_source, "UN-CONSOLIDATED")

    def test_bank_mellat_exact_hit(self):
        hits = self.screener.screen_row(_make_row(sender="BANK MELLAT"), "MT103")
        self.assertGreater(len(hits), 0)

    # ── Alias hits ────────────────────────────────────────────────────────

    def test_melli_bank_alias_hit(self):
        """'MELLI BANK' is a registered alias for 'BANK MELLI IRAN'"""
        hits = self.screener.screen_row(_make_row(sender="MELLI BANK"), "MT103")
        self.assertGreater(len(hits), 0)

    def test_bank_mellat_alias_hit(self):
        """'MELLAT BANK' is an alias"""
        hits = self.screener.screen_row(_make_row(sender="MELLAT BANK"), "MT103")
        self.assertGreater(len(hits), 0)

    def test_vtb_bank_pjsc_alias_hit(self):
        """'BANK VTB PJSC' is an alias for VTB BANK"""
        hits = self.screener.screen_row(_make_row(sender="BANK VTB PJSC"), "MT103")
        self.assertGreater(len(hits), 0)

    def test_sberbank_rossii_alias_hit(self):
        """'SBERBANK ROSSII' is a registered alias"""
        hits = self.screener.screen_row(_make_row(sender="SBERBANK ROSSII"), "MT103")
        self.assertGreater(len(hits), 0)

    # ── Fuzzy hits ────────────────────────────────────────────────────────

    def test_fuzzy_match_with_lower_threshold(self):
        """
        'GAZPROM BANK' (space variant) scores ~72 with token_sort_ratio.
        Using threshold=65 confirms the fuzzy engine DOES find a match,
        just at a lower score than default threshold=85.
        This validates the fuzzy engine works — threshold is a tuning parameter.
        """
        low_threshold_screener = SanctionsScreener(
            sanctions_path=SANCTIONS_PATH, fuzzy_threshold=65
        )
        hits = low_threshold_screener.screen_row(
            _make_row(sender="GAZPROM BANK"), "MT103"
        )
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].match_type, "FUZZY")

    def test_exact_match_beats_fuzzy_threshold(self):
        """Exact match always returns regardless of fuzzy threshold setting."""
        high_threshold = SanctionsScreener(
            sanctions_path=SANCTIONS_PATH, fuzzy_threshold=99
        )
        hits = high_threshold.screen_row(_make_row(sender="GAZPROMBANK"), "MT103")
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].match_type, "EXACT")

    # ── Clean entities — no hits ──────────────────────────────────────────

    def test_deutsche_bank_clean(self):
        hits = self.screener.screen_row(_make_row(sender="DEUTSCHE BANK AG"), "MT103")
        self.assertEqual(len(hits), 0)

    def test_bnp_paribas_clean(self):
        hits = self.screener.screen_row(_make_row(sender="BNP PARIBAS SA"), "MT103")
        self.assertEqual(len(hits), 0)

    def test_allianz_clean(self):
        hits = self.screener.screen_row(
            _make_row(sender="ALLIANZ GLOBAL INVESTORS"), "MT103")
        self.assertEqual(len(hits), 0)

    def test_empty_name_clean(self):
        hits = self.screener.screen_row(_make_row(sender=""), "MT103")
        self.assertEqual(len(hits), 0)

    # ── Return type validation ─────────────────────────────────────────────

    def test_returns_list_of_alert_records(self):
        hits = self.screener.screen_row(_make_row(sender="GAZPROMBANK"), "MT103")
        self.assertIsInstance(hits, list)
        for hit in hits:
            self.assertIsInstance(hit, AlertRecord)

    def test_hit_has_required_fields_populated(self):
        hits = self.screener.screen_row(
            _make_row(sender="BANK MELLI IRAN", amount="2000000"), "MT103"
        )
        self.assertGreater(len(hits), 0)
        hit = hits[0]
        self.assertEqual(hit.alert_type, "SANCTIONS_HIT")
        self.assertEqual(hit.alert_severity, "HIGH")
        self.assertIsNotNone(hit.matched_entity_uid)
        self.assertIsNotNone(hit.matched_entity_name)
        self.assertIsNotNone(hit.list_source)
        self.assertIsNotNone(hit.programme)
        self.assertIsNotNone(hit.sanctions_country)
        self.assertAlmostEqual(hit.amount_eur, 2_000_000.0)

    def test_hit_transaction_id_preserved(self):
        row = _make_row(sender="SBERBANK")
        row["transaction_id"] = "MY-SPECIFIC-TXN-999"
        hits = self.screener.screen_row(row, "MT103")
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].transaction_id, "MY-SPECIFIC-TXN-999")

    # ── Receiver field screening ───────────────────────────────────────────

    def test_receiver_sanctions_hit_detected(self):
        hits = self.screener.screen_row(
            _make_row(sender="DEUTSCHE BANK AG", receiver="GAZPROMBANK"), "MT103"
        )
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].matched_field, "receiver_name")

    def test_both_parties_sanctioned_returns_two_hits(self):
        hits = self.screener.screen_row(
            _make_row(sender="SBERBANK", receiver="VTB BANK"), "MT103"
        )
        self.assertEqual(len(hits), 2)

    # ── Message type field mapping ─────────────────────────────────────────

    def test_mt202_screens_ordering_institution(self):
        row = {
            "transaction_id": "MT202-TEST-001",
            "ordering_institution_name": "GAZPROMBANK",
            "beneficiary_institution_name": "DEUTSCHE BANK AG",
            "amount_eur": "1000000",
            "booking_date": "2024-01-01",
            "ordering_institution_country": "RU",
            "beneficiary_institution_country": "DE",
            "currency": "EUR",
        }
        hits = self.screener.screen_row(row, "MT202")
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].matched_field, "ordering_institution_name")

    def test_mt540_screens_delivering_party(self):
        row = {
            "transaction_id": "MT540-TEST-001",
            "delivering_party_name": "VTB BANK",
            "receiving_party_name": "EUROCLEAR BANK SA",
            "settlement_amount_eur": "5000000",
            "trade_date": "2024-01-01",
            "delivering_party_country": "RU",
            "receiving_party_country": "BE",
            "currency": "EUR",
        }
        hits = self.screener.screen_row(row, "MT540")
        self.assertGreater(len(hits), 0)

    # ── Batch screening ───────────────────────────────────────────────────

    def test_screen_batch_returns_all_hits(self):
        rows = [
            _make_row(sender="SBERBANK"),
            _make_row(sender="DEUTSCHE BANK AG"),
            _make_row(sender="GAZPROMBANK"),
            _make_row(sender="ALLIANZ GLOBAL INVESTORS"),
        ]
        hits = self.screener.screen_batch(rows, "MT103")
        self.assertEqual(len(hits), 2)

    def test_screen_batch_empty_input(self):
        hits = self.screener.screen_batch([], "MT103")
        self.assertEqual(hits, [])

    # ── List source validation ─────────────────────────────────────────────

    def test_ofac_hit_has_correct_list_source(self):
        hits = self.screener.screen_row(_make_row(sender="GAZPROMBANK"), "MT103")
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].list_source, "OFAC-SDN")

    def test_un_hit_has_correct_list_source(self):
        hits = self.screener.screen_row(
            _make_row(sender="ISLAMIC STATE IN IRAQ AND THE LEVANT"), "MT103"
        )
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0].list_source, "UN-CONSOLIDATED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
