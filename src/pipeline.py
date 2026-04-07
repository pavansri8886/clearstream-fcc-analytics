"""
pipeline.py
-----------
Main AML processing pipeline.

Reads all three transaction files in 10,000-row chunks.
Normalises field names so every row uses sender_name / receiver_name.
Runs sanctions screening + all AML detectors per chunk.
Writes alerts to data/processed/alerts.csv.

Usage:
    python src/pipeline.py                   # full run
    python src/pipeline.py --dry-run         # first 1,000 rows per file
    python src/pipeline.py --file mt103      # single file
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config import CFG
from schema import ALERT_COLUMNS, AlertRecord
from screener import SanctionsScreener
from detectors import (
    StructuringDetector,
    VelocityDetector,
    LargeTransactionDetector,
    HighRiskCorridorDetector,
)

# ── File registry — driven by settings.yaml ────────────────────────────────
FILES = {
    "mt103": (ROOT / CFG["paths"]["mt103"], "MT103"),
    "mt202": (ROOT / CFG["paths"]["mt202"], "MT202"),
    "mt540": (ROOT / CFG["paths"]["mt540"], "MT540"),
}

OUTPUT_PATH  = ROOT / CFG["paths"]["alerts_output"]
SUMMARY_PATH = ROOT / CFG["paths"]["summary_output"]
CHUNK_SIZE   = CFG["pipeline"]["chunk_size"]


# ── Field normalisation ────────────────────────────────────────────────────
# MT202 and MT540 use different column names for the same concepts.
# We rename them to standard names once here so every downstream file
# (screener, detectors) can always use sender_name / receiver_name.

_RENAME = {
    "MT202": {
        "ordering_institution_name":       "sender_name",
        "ordering_institution_country":    "sender_country",
        "beneficiary_institution_name":    "receiver_name",
        "beneficiary_institution_country": "receiver_country",
    },
    "MT540": {
        "delivering_party_name":    "sender_name",
        "delivering_party_country": "sender_country",
        "receiving_party_name":     "receiver_name",
        "receiving_party_country":  "receiver_country",
        "settlement_amount_eur":    "amount_eur",
        "trade_date":               "booking_date",
    },
}

def _normalize_row(row: dict, msg_type: str) -> dict:
    """Rename message-type-specific fields to standard names in-place."""
    for old, new in _RENAME.get(msg_type, {}).items():
        if old in row and new not in row:
            row[new] = row.pop(old)
    return row


# ── Stats dataclass ────────────────────────────────────────────────────────

@dataclass
class PipelineStats:
    total_rows:      int = 0
    total_alerts:    int = 0
    sanctions:       int = 0
    structuring:     int = 0
    velocity:        int = 0
    large_txn:       int = 0
    high_risk:       int = 0
    high_severity:   int = 0
    medium_severity: int = 0
    sar_candidates:  int = 0
    by_file:         dict = field(default_factory=dict)


# ── Chunk reader ───────────────────────────────────────────────────────────

def read_chunks(filepath: Path, chunk_size: int, max_rows: int = None):
    """Yield lists of row-dicts, chunk_size at a time."""
    rows_read = 0
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        chunk = []
        for row in reader:
            chunk.append(row)
            rows_read += 1
            if len(chunk) == chunk_size:
                yield chunk
                chunk = []
            if max_rows and rows_read >= max_rows:
                if chunk:
                    yield chunk
                return
        if chunk:
            yield chunk


def count_rows(filepath: Path) -> int:
    with open(filepath, newline="", encoding="utf-8") as f:
        return sum(1 for _ in f) - 1


# ── Pipeline ───────────────────────────────────────────────────────────────

class FccPipeline:

    def __init__(self, chunk_size=CHUNK_SIZE, fuzzy_threshold=None,
                 dry_run=False, files=None):
        self.chunk_size   = chunk_size
        self.dry_run      = dry_run
        self.max_rows     = 1_000 if dry_run else None
        self.target_files = files or list(FILES.keys())

        fuzzy_threshold = fuzzy_threshold or CFG["pipeline"]["fuzzy_match_threshold"]

        print("\n" + "="*60)
        print("  Clearstream FCC Analytics — AML Pipeline")
        print("="*60)
        if dry_run:
            print("  DRY RUN — 1,000 rows per file")
        print()

        self.screener    = SanctionsScreener(fuzzy_threshold=fuzzy_threshold)
        self.structuring = StructuringDetector()
        self.velocity    = VelocityDetector()
        self.large_txn   = LargeTransactionDetector()
        self.high_risk   = HighRiskCorridorDetector()

        self.stats = PipelineStats()

    # ── Run ────────────────────────────────────────────────────────────────

    def run(self) -> None:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as out_f:
            writer = csv.DictWriter(out_f, fieldnames=ALERT_COLUMNS,
                                    extrasaction="ignore")
            writer.writeheader()

            for file_key in self.target_files:
                filepath, msg_type = FILES[file_key]

                if not filepath.exists():
                    print(f"\n  Not found: {filepath}")
                    continue

                total     = count_rows(filepath)
                effective = min(total, self.max_rows) if self.max_rows else total
                n_chunks  = -(-effective // self.chunk_size)

                print(f"\n  {file_key.upper()} — {effective:,} rows")
                file_alerts = 0

                for chunk in tqdm(read_chunks(filepath, self.chunk_size, self.max_rows),
                                  total=n_chunks, unit="chunk", desc=f"  {file_key}"):
                    # Normalise field names before any detection
                    chunk = [_normalize_row(row, msg_type) for row in chunk]

                    alerts = self._process_chunk(chunk, msg_type)
                    for alert in alerts:
                        alert.enrich_derived_fields()
                        writer.writerow(alert.to_dict())

                    file_alerts           += len(alerts)
                    self.stats.total_rows += len(chunk)

                print(f"    {file_alerts:,} alerts")
                self.stats.total_alerts += file_alerts
                self.stats.by_file[file_key] = {"rows": effective, "alerts": file_alerts}

        self._write_summary()
        self._print_summary()

    # ── Chunk processing ───────────────────────────────────────────────────

    def _process_chunk(self, chunk: list[dict], msg_type: str) -> list[AlertRecord]:
        alerts: list[AlertRecord] = []

        # 1. Sanctions screening
        for alert in self.screener.screen_batch(chunk, msg_type):
            self.stats.sanctions     += 1
            self.stats.high_severity += 1
            if alert.is_sar_candidate:
                self.stats.sar_candidates += 1
            alerts.append(alert)

        # 2. Rule-based detectors
        df = pd.DataFrame(chunk)

        if msg_type == "MT103":
            for a in self.structuring.detect(df):
                self.stats.structuring   += 1
                self.stats.high_severity += 1
                alerts.append(a)

        if msg_type in ("MT103", "MT202"):
            for a in self.velocity.detect(df):
                self.stats.velocity      += 1
                self.stats.high_severity += 1
                alerts.append(a)

        # Large transaction threshold only meaningful for retail MT103 transfers.
        # MT202 and MT540 are inter-bank/securities where large amounts are normal.
        if msg_type == "MT103":
            for a in self.large_txn.detect(df):
                self.stats.large_txn += 1
                if a.alert_severity == "HIGH":
                    self.stats.high_severity   += 1
                else:
                    self.stats.medium_severity += 1
                alerts.append(a)

        for a in self.high_risk.detect(df):
            self.stats.high_risk       += 1
            self.stats.medium_severity += 1
            alerts.append(a)

        return alerts

    # ── Summary ────────────────────────────────────────────────────────────

    def _write_summary(self) -> None:
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        s = self.stats
        rows = [
            {"metric": "Total Rows Processed",     "value": s.total_rows},
            {"metric": "Total Alerts Generated",    "value": s.total_alerts},
            {"metric": "Alert Rate (%)",            "value": round(s.total_alerts / max(s.total_rows, 1) * 100, 2)},
            {"metric": "Sanctions Hits",            "value": s.sanctions},
            {"metric": "Structuring Alerts",        "value": s.structuring},
            {"metric": "Velocity Alerts",           "value": s.velocity},
            {"metric": "Large Transaction Alerts",  "value": s.large_txn},
            {"metric": "High-Risk Corridor Alerts", "value": s.high_risk},
            {"metric": "HIGH Severity Alerts",      "value": s.high_severity},
            {"metric": "MEDIUM Severity Alerts",    "value": s.medium_severity},
            {"metric": "SAR Candidates",            "value": s.sar_candidates},
        ]
        with open(SUMMARY_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["metric", "value"])
            w.writeheader()
            w.writerows(rows)

    def _print_summary(self) -> None:
        s = self.stats
        rate = s.total_alerts / max(s.total_rows, 1) * 100
        print(f"""
{'='*60}
  PIPELINE COMPLETE
{'='*60}
  Rows processed      {s.total_rows:>10,}
  Total alerts        {s.total_alerts:>10,}  ({rate:.2f}%)
{'─'*60}
  Sanctions hits      {s.sanctions:>10,}
  Structuring         {s.structuring:>10,}
  Velocity            {s.velocity:>10,}
  Large transactions  {s.large_txn:>10,}
  High-risk corridor  {s.high_risk:>10,}
{'─'*60}
  HIGH severity       {s.high_severity:>10,}
  MEDIUM severity     {s.medium_severity:>10,}
  SAR candidates      {s.sar_candidates:>10,}
{'─'*60}
  Output  → {OUTPUT_PATH}
  Summary → {SUMMARY_PATH}
{'='*60}
""")


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",         action="store_true")
    parser.add_argument("--file",            choices=["mt103", "mt202", "mt540"])
    parser.add_argument("--chunk-size",      type=int, default=CHUNK_SIZE)
    parser.add_argument("--fuzzy-threshold", type=int, default=None)
    args = parser.parse_args()

    FccPipeline(
        chunk_size=args.chunk_size,
        fuzzy_threshold=args.fuzzy_threshold,
        dry_run=args.dry_run,
        files=[args.file] if args.file else None,
    ).run()


if __name__ == "__main__":
    main()
