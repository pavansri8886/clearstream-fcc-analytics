"""
pipeline.py
-----------
Main AML processing pipeline.

Reads all three transaction files in 10,000-row chunks.
Runs sanctions screening + all AML detectors per chunk.
Enriches every AlertRecord with derived fields (month, corridor, days_open).
Writes alerts incrementally to data/processed/alerts.csv.

Usage:
    python src/pipeline.py                     # full 600k run (~3-5 min)
    python src/pipeline.py --dry-run           # first 1,000 rows per file
    python src/pipeline.py --file mt103        # single file
    python src/pipeline.py --chunk-size 5000   # smaller memory footprint
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from schema import ALERT_COLUMNS, AlertRecord
from screener import SanctionsScreener
from detectors import (
    StructuringDetector,
    VelocityDetector,
    LargeTransactionDetector,
    HighRiskCorridorDetector,
)

# ── File registry ──────────────────────────────────────────────────────────
FILES = {
    "mt103": (ROOT / "data" / "generated" / "transactions_mt103.csv", "MT103"),
    "mt202": (ROOT / "data" / "generated" / "transactions_mt202.csv", "MT202"),
    "mt540": (ROOT / "data" / "generated" / "transactions_mt540.csv", "MT540"),
}

OUTPUT_PATH  = ROOT / "data" / "processed" / "alerts.csv"
SUMMARY_PATH = ROOT / "data" / "processed" / "summary_stats.csv"
CHUNK_SIZE   = 10_000


# ── Chunk reader ───────────────────────────────────────────────────────────

def read_chunks(filepath: Path, chunk_size: int,
                max_rows: int = None):
    """Yield lists of row dicts, chunk_size at a time. Never loads full file."""
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

    def __init__(self, chunk_size=CHUNK_SIZE, fuzzy_threshold=85,
                 dry_run=False, files=None):
        self.chunk_size      = chunk_size
        self.dry_run         = dry_run
        self.max_rows        = 1_000 if dry_run else None
        self.target_files    = files or list(FILES.keys())

        print("\n" + "="*60)
        print("  Clearstream FCC Analytics — AML Pipeline")
        print("="*60)
        if dry_run:
            print("  ⚡ DRY RUN — 1,000 rows per file")
        print()

        # Components
        self.screener    = SanctionsScreener(fuzzy_threshold=fuzzy_threshold)
        self.structuring = StructuringDetector()
        self.velocity    = VelocityDetector()
        self.large_txn   = LargeTransactionDetector()
        self.high_risk   = HighRiskCorridorDetector()

        # Stats — tracked across all files
        self.stats = {
            "total_rows":       0,
            "total_alerts":     0,
            "sanctions":        0,
            "structuring":      0,
            "velocity":         0,
            "large_txn":        0,
            "high_risk":        0,
            "high_severity":    0,
            "medium_severity":  0,
            "sar_candidates":   0,
            "by_file":          {},
        }

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
                    print(f"\n  ⚠ Not found: {filepath}")
                    print(f"    Run: python scripts/generate_transactions.py")
                    continue

                total     = count_rows(filepath)
                effective = min(total, self.max_rows) if self.max_rows else total
                print(f"\n  ▶ {file_key.upper()} — {effective:,} rows")

                file_alerts = 0
                chunk_num   = 0
                t0          = time.time()

                for chunk in read_chunks(filepath, self.chunk_size, self.max_rows):
                    chunk_num += 1
                    alerts = self._process_chunk(chunk, msg_type)

                    for alert in alerts:
                        # Enrich derived fields
                        alert.enrich_derived_fields()
                        writer.writerow(alert.to_dict())

                    file_alerts              += len(alerts)
                    self.stats["total_rows"] += len(chunk)

                    pct     = min(chunk_num * self.chunk_size / effective * 100, 100)
                    elapsed = time.time() - t0
                    print(
                        f"\r    chunk {chunk_num:4d} | "
                        f"{min(chunk_num*self.chunk_size, effective):>8,}/"
                        f"{effective:,} | {pct:5.1f}% | "
                        f"{elapsed:5.1f}s | {file_alerts:,} alerts",
                        end="", flush=True,
                    )

                print(f"\n    ✓ {file_alerts:,} alerts")
                self.stats["total_alerts"] += file_alerts
                self.stats["by_file"][file_key] = {
                    "rows": effective, "alerts": file_alerts
                }

        self._write_summary()
        self._print_summary()

    # ── Chunk processing ───────────────────────────────────────────────────

    def _process_chunk(self, chunk: list[dict],
                       msg_type: str) -> list[AlertRecord]:
        import pandas as pd

        alerts: list[AlertRecord] = []

        # 1. Sanctions screening (pure Python — no pandas)
        for alert in self.screener.screen_batch(chunk, msg_type):
            self.stats["sanctions"]     += 1
            self.stats["high_severity"] += 1
            if alert.is_sar_candidate:
                self.stats["sar_candidates"] += 1
            alerts.append(alert)

        # 2. Rule-based detectors (pandas DataFrame)
        df = pd.DataFrame(chunk)

        # Structuring — MT103 only
        if msg_type == "MT103":
            for a in self.structuring.detect(df):
                self.stats["structuring"] += 1
                self.stats["high_severity"] += 1
                alerts.append(a)

        # Velocity — MT103 + MT202
        if msg_type in ("MT103", "MT202"):
            for a in self.velocity.detect(df):
                self.stats["velocity"] += 1
                self.stats["high_severity"] += 1
                alerts.append(a)

        # Large transactions — all files
        for a in self.large_txn.detect(df):
            self.stats["large_txn"] += 1
            if a.alert_severity == "HIGH":
                self.stats["high_severity"] += 1
            else:
                self.stats["medium_severity"] += 1
            alerts.append(a)

        # High-risk corridor — all files
        for a in self.high_risk.detect(df):
            self.stats["high_risk"]        += 1
            self.stats["medium_severity"]  += 1
            alerts.append(a)

        return alerts

    # ── Summary ────────────────────────────────────────────────────────────

    def _write_summary(self) -> None:
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        s = self.stats
        total  = s["total_rows"]
        alerts = s["total_alerts"]
        rows = [
            {"metric": "Total Rows Processed",        "value": total},
            {"metric": "Total Alerts Generated",       "value": alerts},
            {"metric": "Alert Rate (%)",               "value": round(alerts/max(total,1)*100, 2)},
            {"metric": "Sanctions Hits",               "value": s["sanctions"]},
            {"metric": "Structuring Alerts",           "value": s["structuring"]},
            {"metric": "Velocity Alerts",              "value": s["velocity"]},
            {"metric": "Large Transaction Alerts",     "value": s["large_txn"]},
            {"metric": "High-Risk Corridor Alerts",    "value": s["high_risk"]},
            {"metric": "HIGH Severity Alerts",         "value": s["high_severity"]},
            {"metric": "MEDIUM Severity Alerts",       "value": s["medium_severity"]},
            {"metric": "SAR Candidates",               "value": s["sar_candidates"]},
        ]
        with open(SUMMARY_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["metric", "value"])
            w.writeheader()
            w.writerows(rows)

    def _print_summary(self) -> None:
        s = self.stats
        rate = s["total_alerts"] / max(s["total_rows"], 1) * 100
        print(f"""
{'='*60}
  PIPELINE COMPLETE
{'='*60}
  Rows processed      {s['total_rows']:>10,}
  Total alerts        {s['total_alerts']:>10,}  ({rate:.2f}%)
{'─'*60}
  Sanctions hits      {s['sanctions']:>10,}
  Structuring         {s['structuring']:>10,}
  Velocity            {s['velocity']:>10,}
  Large transactions  {s['large_txn']:>10,}
  High-risk corridor  {s['high_risk']:>10,}
{'─'*60}
  HIGH severity       {s['high_severity']:>10,}
  MEDIUM severity     {s['medium_severity']:>10,}
  SAR candidates      {s['sar_candidates']:>10,}
{'─'*60}
  Output  → {OUTPUT_PATH}
  Summary → {SUMMARY_PATH}
{'='*60}
""")


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",        action="store_true")
    parser.add_argument("--file",           choices=["mt103","mt202","mt540"])
    parser.add_argument("--chunk-size",     type=int, default=CHUNK_SIZE)
    parser.add_argument("--fuzzy-threshold",type=int, default=85)
    args = parser.parse_args()

    FccPipeline(
        chunk_size=args.chunk_size,
        fuzzy_threshold=args.fuzzy_threshold,
        dry_run=args.dry_run,
        files=[args.file] if args.file else None,
    ).run()


if __name__ == "__main__":
    main()
