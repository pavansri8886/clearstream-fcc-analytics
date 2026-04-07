"""
screener.py
-----------
Sanctions screening engine.

Screens transaction counterparties against the combined sanctions master
list (OFAC SDN + UN Consolidated + EU FSF).

Two matching modes:
  1. Exact match  — uppercase normalised string comparison (fast)
  2. Fuzzy match  — token_sort_ratio for name variations and typos
                    e.g. "GAZPROM BANK" matches "GAZPROMBANK" at score 95

Returns AlertRecord objects (from schema.py) — same type as detectors.py.
Pipeline receives one consistent type from both sources.

Usage (test):
    python src/screener.py
"""

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config import CFG
from schema import AlertRecord, determine_severity, _safe_float, _safe_str

# ── Fuzzy backend ──────────────────────────────────────────────────────────
try:
    from rapidfuzz import fuzz, process as fuzz_process
    FUZZY_BACKEND = "rapidfuzz"
except ImportError:
    fuzz_process = None
    FUZZY_BACKEND = "difflib"

SANCTIONS_PATH = ROOT / CFG["paths"]["sanctions_master"]

# After pipeline normalisation, every message type uses these two fields.
FIELDS_TO_SCREEN = ["sender_name", "receiver_name"]


@dataclass
class SanctionedEntity:
    uid: str
    canonical_name: str
    all_names: list[str]
    entity_type: str
    country: str
    country_full: str
    programme: str
    list_source: str
    listing_date: str
    remarks: str


class SanctionsScreener:
    """
    Loads combined_master.csv once into memory (37 rows — tiny).
    Screens any transaction row against all sanctioned entity names
    and aliases. Returns list[AlertRecord].
    """

    def __init__(
        self,
        sanctions_path: Path = SANCTIONS_PATH,
        fuzzy_threshold: int = 85,
    ):
        self.fuzzy_threshold = fuzzy_threshold
        self._entities: list[SanctionedEntity] = []
        self._load(sanctions_path)

        # Pre-build lookup structures for fast matching:
        # _exact_lookup: normalised_alias → entity  (O(1) exact match)
        # _all_aliases:  flat list of normalised aliases for process.extractOne
        # _alias_to_entity: normalised_alias → entity (for fuzzy result lookup)
        self._exact_lookup: dict[str, SanctionedEntity] = {}
        self._all_aliases:  list[str] = []
        self._alias_to_entity: dict[str, SanctionedEntity] = {}
        for entity in self._entities:
            for alias in entity.all_names:
                norm = self._normalise(alias)
                self._exact_lookup[norm] = entity
                self._all_aliases.append(norm)
                self._alias_to_entity[norm] = entity

        print(f"  [Screener] {len(self._entities)} sanctioned entities loaded "
              f"| {len(self._all_aliases)} aliases | backend: {FUZZY_BACKEND} "
              f"| threshold: {fuzzy_threshold}")

    # ── Public ────────────────────────────────────────────────────────────

    def screen_row(self, row: dict, message_type: str) -> list[AlertRecord]:
        """Screen one transaction row. Returns list of AlertRecord (empty = clean)."""
        alerts = []

        for field_name in FIELDS_TO_SCREEN:
            name = (row.get(field_name) or "").strip()
            if not name:
                continue

            entity = self._match(name)
            if entity is None:
                continue

            match_type, score = self._score(name, entity)
            amount   = _safe_float(row.get("amount_eur"))
            severity = determine_severity("SANCTIONS_HIT", amount)

            sender_name     = _safe_str(row.get("sender_name"))
            sender_country  = _safe_str(row.get("sender_country"))
            receiver_name   = _safe_str(row.get("receiver_name"))
            receiver_country = _safe_str(row.get("receiver_country"))

            alert = AlertRecord(
                transaction_id=_safe_str(row.get("transaction_id")),
                message_type=message_type,
                alert_type="SANCTIONS_HIT",
                alert_severity=severity,
                aml_typology="SANCTIONS_EVASION",
                amount_eur=amount,
                currency=_safe_str(row.get("currency", "EUR")),
                booking_date=_safe_str(row.get("booking_date")
                                       or row.get("trade_date", "")),
                sender_name=sender_name,
                sender_country=sender_country,
                receiver_name=receiver_name,
                receiver_country=receiver_country,
                description=(
                    f"Sanctions hit: '{name}' matched '{entity.canonical_name}' "
                    f"[{match_type}, score {score}] on {entity.list_source} "
                    f"/ {entity.programme} programme."
                ),
                # Sanctions-specific
                matched_field=field_name,
                matched_value=name,
                matched_entity_uid=entity.uid,
                matched_entity_name=entity.canonical_name,
                match_type=match_type,
                match_score=score,
                list_source=entity.list_source,
                programme=entity.programme,
                sanctions_country=entity.country,
            )
            alerts.append(alert)

        return alerts

    def screen_batch(self, rows: list[dict], message_type: str) -> list[AlertRecord]:
        alerts = []
        for row in rows:
            alerts.extend(self.screen_row(row, message_type))
        return alerts

    # ── Matching ─────────────────────────────────────────────────────────

    def _normalise(self, name: str) -> str:
        name = name.upper().strip()
        name = re.sub(r"[.,\-_/\\()]", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def _match(self, name: str) -> Optional[SanctionedEntity]:
        norm = self._normalise(name)

        # O(1) exact lookup — replaces the old O(n×m) loop
        if norm in self._exact_lookup:
            return self._exact_lookup[norm]

        # Fuzzy lookup — rapidfuzz.process searches all aliases in C, not Python
        if FUZZY_BACKEND == "rapidfuzz":
            result = fuzz_process.extractOne(
                norm, self._all_aliases,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=self.fuzzy_threshold,
            )
            if result:
                matched_alias, score, _ = result
                return self._alias_to_entity[matched_alias]
            return None

        # Fallback: difflib (slow — only used if rapidfuzz not installed)
        best_score, best_alias = 0, None
        for alias in self._all_aliases:
            s = int(__import__("difflib").SequenceMatcher(None, norm, alias).ratio() * 100)
            if s > best_score:
                best_score, best_alias = s, alias
        return self._alias_to_entity[best_alias] if best_score >= self.fuzzy_threshold else None

    def _score(self, name: str, entity: SanctionedEntity) -> tuple[str, int]:
        norm = self._normalise(name)
        if norm in self._exact_lookup and self._exact_lookup[norm] is entity:
            return "EXACT", 100
        if FUZZY_BACKEND == "rapidfuzz":
            aliases = [self._normalise(a) for a in entity.all_names]
            result = fuzz_process.extractOne(norm, aliases, scorer=fuzz.token_sort_ratio)
            return "FUZZY", result[1] if result else 0
        scores = [int(__import__("difflib").SequenceMatcher(None, norm, self._normalise(a)).ratio() * 100)
                  for a in entity.all_names]
        return "FUZZY", max(scores)

    # ── Loader ────────────────────────────────────────────────────────────

    def _load(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(
                f"Sanctions master list not found: {path}\n"
                "Run: python scripts/build_sanctions_lists.py"
            )
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                names = [n.strip() for n in row["all_names"].split("|") if n.strip()]
                self._entities.append(SanctionedEntity(
                    uid=row["uid"],
                    canonical_name=row["canonical_name"],
                    all_names=names,
                    entity_type=row["type"],
                    country=row["country"],
                    country_full=row["country_full"],
                    programme=row["programme"],
                    list_source=row["list_source"],
                    listing_date=row["listing_date"],
                    remarks=row["remarks"],
                ))


# ── Quick test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🔍 Screener — Quick Test\n")
    screener = SanctionsScreener()

    cases = [
        ("BANK MELLI IRAN",    True,  "OFAC exact"),
        ("GAZPROMBANK",        True,  "OFAC exact"),
        ("GAZPROM BANK",       True,  "Fuzzy alias"),
        ("VTB BANK",           True,  "OFAC + EU"),
        ("MELLI BANK",         True,  "Alias match"),
        ("ALLIANZ GLOBAL INVESTORS", False, "Clean entity"),
        ("DEUTSCHE BANK AG",   False, "Clean entity"),
        ("BNP PARIBAS SA",     False, "Clean entity"),
    ]

    passed = 0
    for name, expect_hit, note in cases:
        row = {"transaction_id": "TEST-001",
               "sender_name": name, "receiver_name": "DEUTSCHE BANK AG",
               "amount_eur": "1000000", "booking_date": "2024-01-01",
               "sender_country": "DE", "receiver_country": "LU"}
        hits = screener.screen_row(row, "MT103")
        got = len(hits) > 0
        ok = got == expect_hit
        if ok:
            passed += 1
        status = "✓" if ok else "✗"
        detail = f"→ {hits[0].matched_entity_name} [{hits[0].match_type}]" if hits else "→ CLEAN"
        print(f"  {status} [{note}] '{name}' {detail}")

    print(f"\n  {passed}/{len(cases)} passed\n")
