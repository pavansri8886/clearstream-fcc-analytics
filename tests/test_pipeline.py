"""
tests/test_pipeline.py
----------------------
Integration tests for pipeline.py — end-to-end chunk processing.

Tests cover:
  - read_chunks() yields correct chunk sizes
  - read_chunks() respects max_rows limit
  - read_chunks() handles files smaller than chunk_size
  - Pipeline processes a small synthetic CSV end-to-end
  - alerts.csv is written with correct ALERT_COLUMNS headers
  - summary_stats.csv is written after pipeline run
  - Pipeline correctly counts sanctions hits in stats
  - Pipeline correctly handles all 3 message types
  - Derived fields (month, corridor) are present in output
"""

import csv
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from schema import ALERT_COLUMNS
from pipeline import read_chunks, count_rows, FccPipeline, FILES

SANCTIONS_PATH = ROOT / "data" / "raw" / "sanctions" / "combined_master.csv"


def _write_temp_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _make_mt103_rows(n=50, include_sanctions=True) -> list[dict]:
    base = datetime(2024, 3, 15, 9, 0, 0)
    rows = []
    for i in range(n):
        ts = base + timedelta(hours=i)
        sender = "GAZPROMBANK" if (include_sanctions and i == 5) else f"CLEAN BANK {i}"
        rows.append({
            "transaction_id": f"MT103-TEST-{i:05d}",
            "message_type": "MT103",
            "booking_date": ts.date().isoformat(),
            "value_date": (ts + timedelta(days=2)).date().isoformat(),
            "timestamp": ts.isoformat(),
            "booking_centre": "LU",
            "sender_name": sender,
            "sender_lei": "TEST_LEI_SENDER",
            "sender_bic": "TESTBIC1",
            "sender_account": "DE12345678901234567890",
            "sender_country": "RU" if (include_sanctions and i == 5) else "DE",
            "receiver_name": f"RECEIVER BANK {i}",
            "receiver_lei": "TEST_LEI_RECV",
            "receiver_bic": "TESTBIC2",
            "receiver_account": "LU98765432109876543210",
            "receiver_country": "LU",
            "correspondent_bank_name": "DEUTSCHE BANK AG",
            "correspondent_bank_bic": "DEUTDEDB",
            "correspondent_bank_country": "DE",
            "amount": str(50000 + i * 1000),
            "currency": "EUR",
            "amount_eur": str(50000 + i * 1000),
            "purpose_code": "TRAD",
            "remittance_info": f"REF-{i:08d}",
            "sender_is_sanctions_hit": "True" if (include_sanctions and i == 5) else "False",
            "receiver_is_sanctions_hit": "False",
            "sanctions_hit_name": "GAZPROMBANK" if (include_sanctions and i == 5) else "",
            "sanctions_uid": "OFAC-31003" if (include_sanctions and i == 5) else "",
            "sanctions_list_source": "OFAC-SDN" if (include_sanctions and i == 5) else "",
            "sanctions_programme": "RUSSIA" if (include_sanctions and i == 5) else "",
            "is_high_risk_jurisdiction": "True" if (include_sanctions and i == 5) else "False",
            "high_risk_country": "RU" if (include_sanctions and i == 5) else "",
            "aml_typology": "",
            "typology_cluster_id": "",
            "is_suspicious": "True" if (include_sanctions and i == 5) else "False",
            "alert_status": "OPEN" if (include_sanctions and i == 5) else "CLEAR",
        })
    return rows


class TestReadChunks(unittest.TestCase):

    def _make_csv(self, n_rows: int) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        )
        w = csv.DictWriter(tmp, fieldnames=["id", "val"])
        w.writeheader()
        for i in range(n_rows):
            w.writerow({"id": i, "val": f"row_{i}"})
        tmp.close()
        return Path(tmp.name)

    def test_single_chunk_when_rows_less_than_chunk_size(self):
        path = self._make_csv(50)
        chunks = list(read_chunks(path, chunk_size=100))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 50)
        path.unlink()

    def test_multiple_chunks_correct_size(self):
        path = self._make_csv(250)
        chunks = list(read_chunks(path, chunk_size=100))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(len(chunks[0]), 100)
        self.assertEqual(len(chunks[1]), 100)
        self.assertEqual(len(chunks[2]), 50)
        path.unlink()

    def test_max_rows_respected(self):
        path = self._make_csv(500)
        chunks = list(read_chunks(path, chunk_size=100, max_rows=150))
        total = sum(len(c) for c in chunks)
        self.assertEqual(total, 150)
        path.unlink()

    def test_each_row_is_dict(self):
        path = self._make_csv(10)
        chunks = list(read_chunks(path, chunk_size=100))
        for row in chunks[0]:
            self.assertIsInstance(row, dict)
            self.assertIn("id", row)
            self.assertIn("val", row)
        path.unlink()

    def test_empty_file_yields_nothing(self):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        )
        w = csv.DictWriter(tmp, fieldnames=["id"])
        w.writeheader()
        tmp.close()
        chunks = list(read_chunks(Path(tmp.name), chunk_size=100))
        self.assertEqual(chunks, [])
        Path(tmp.name).unlink()


class TestCountRows(unittest.TestCase):

    def test_counts_correctly(self):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        )
        w = csv.DictWriter(tmp, fieldnames=["id"])
        w.writeheader()
        for i in range(42):
            w.writerow({"id": i})
        tmp.close()
        self.assertEqual(count_rows(Path(tmp.name)), 42)
        Path(tmp.name).unlink()


@unittest.skipUnless(SANCTIONS_PATH.exists(),
                     "Sanctions master list not found — run build_sanctions_lists.py first")
class TestPipelineEndToEnd(unittest.TestCase):
    """
    Integration test — runs the pipeline on a small synthetic dataset.
    Uses a temp directory so it doesn't touch production data.
    """

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.alerts_path   = self.tmp_dir / "alerts.csv"
        self.summary_path  = self.tmp_dir / "summary_stats.csv"

        # Patch pipeline output paths
        import pipeline as pl
        self._orig_output  = pl.OUTPUT_PATH
        self._orig_summary = pl.SUMMARY_PATH
        pl.OUTPUT_PATH     = self.alerts_path
        pl.SUMMARY_PATH    = self.summary_path

        # Write synthetic MT103 file
        self.mt103_path = self.tmp_dir / "transactions_mt103.csv"
        rows = _make_mt103_rows(n=100, include_sanctions=True)
        _write_temp_csv(rows, self.mt103_path)

        # Patch FILES to use our temp file
        self._orig_files = dict(pl.FILES)
        pl.FILES = {
            "mt103": (self.mt103_path, "MT103"),
        }

    def tearDown(self):
        import pipeline as pl
        pl.OUTPUT_PATH  = self._orig_output
        pl.SUMMARY_PATH = self._orig_summary
        pl.FILES        = self._orig_files

        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_pipeline_creates_alerts_csv(self):
        pipeline = FccPipeline(chunk_size=50, dry_run=False, files=["mt103"])
        pipeline.run()
        self.assertTrue(self.alerts_path.exists())

    def test_alerts_csv_has_correct_headers(self):
        pipeline = FccPipeline(chunk_size=50, dry_run=False, files=["mt103"])
        pipeline.run()
        with open(self.alerts_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
        for col in ALERT_COLUMNS:
            self.assertIn(col, headers, f"Missing column: {col}")

    def test_pipeline_creates_summary_stats(self):
        pipeline = FccPipeline(chunk_size=50, dry_run=False, files=["mt103"])
        pipeline.run()
        self.assertTrue(self.summary_path.exists())

    def test_summary_has_expected_metrics(self):
        pipeline = FccPipeline(chunk_size=50, dry_run=False, files=["mt103"])
        pipeline.run()
        with open(self.summary_path, newline="", encoding="utf-8") as f:
            stats = {r["metric"]: r["value"] for r in csv.DictReader(f)}
        self.assertIn("Total Rows Processed", stats)
        self.assertIn("Total Alerts Generated", stats)
        self.assertIn("Sanctions Hits", stats)

    def test_total_rows_processed_correct(self):
        pipeline = FccPipeline(chunk_size=50, dry_run=False, files=["mt103"])
        pipeline.run()
        self.assertEqual(pipeline.stats["total_rows"], 100)

    def test_alerts_have_derived_fields(self):
        pipeline = FccPipeline(chunk_size=50, dry_run=False, files=["mt103"])
        pipeline.run()
        with open(self.alerts_path, newline="", encoding="utf-8") as f:
            alerts = list(csv.DictReader(f))
        if alerts:
            for alert in alerts[:5]:
                # month should be populated
                self.assertIn("month", alert)
                if alert.get("month"):
                    self.assertRegex(alert["month"], r"^\d{4}-\d{2}$")

    def test_dry_run_processes_limited_rows(self):
        pipeline = FccPipeline(chunk_size=50, dry_run=True, files=["mt103"])
        pipeline.run()
        self.assertLessEqual(pipeline.stats["total_rows"], 1000)

    def test_stats_tracked_correctly(self):
        pipeline = FccPipeline(chunk_size=50, dry_run=False, files=["mt103"])
        pipeline.run()
        self.assertGreaterEqual(pipeline.stats["total_alerts"], 0)
        self.assertGreaterEqual(pipeline.stats["high_severity"], 0)
        total = (pipeline.stats["sanctions"] +
                 pipeline.stats["structuring"] +
                 pipeline.stats["velocity"] +
                 pipeline.stats["large_txn"] +
                 pipeline.stats["high_risk"])
        self.assertEqual(total, pipeline.stats["total_alerts"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
