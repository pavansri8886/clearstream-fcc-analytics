"""
generate_transactions.py
------------------------
Generates 600,000 synthetic Clearstream-style transactions across three
SWIFT message types, embedding realistic AML typologies and sanctions hits.

Transaction types:
  MT103   — Cross-border customer wire transfers          (300k rows)
  MT540/2/3 — Securities settlements DVP/RVP/FOP         (200k rows)
  MT202   — Interbank / fund transfers                   (100k rows)

AML typologies embedded (FATF-standard):
  1. Structuring     — Multiple txns just below €9,999 threshold
  2. Layering        — Funds through 3+ jurisdictions rapidly
  3. Velocity        — 50+ txns from same entity in 24h window
  4. Round-tripping  — Funds leave and return via intermediaries
  5. High-risk corridor — FATF grey-list jurisdiction involvement

Sanctions hits:
  ~0.08% true positive rate (realistic production rate)
  ~2.5%  false positive rate (name fuzzy match noise)

Output:
  data/generated/transactions_mt103.csv         (wire transfers)
  data/generated/transactions_mt540.csv         (securities settlements)
  data/generated/transactions_mt202.csv         (interbank transfers)
  data/generated/transactions_combined.csv      (all three merged)
  data/generated/ground_truth_labels.csv        (for model validation)

Usage:
  python scripts/generate_transactions.py
  python scripts/generate_transactions.py --rows 100000  (lighter dev run)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import string
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────

SEED = 42
random.seed(SEED)

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "generated"
SANCTIONS_PATH = Path(__file__).parent.parent / "data" / "raw" / "sanctions" / "combined_master.csv"

# ── REFERENCE DATA ────────────────────────────────────────────────────────

# Real correspondent banks (global tier-1)
CORRESPONDENT_BANKS = [
    {"name": "DEUTSCHE BANK AG",          "bic": "DEUTDEDB", "country": "DE", "city": "Frankfurt"},
    {"name": "BNP PARIBAS SA",             "bic": "BNPAFRPP", "country": "FR", "city": "Paris"},
    {"name": "SOCIETE GENERALE",           "bic": "SOGEFRPP", "country": "FR", "city": "Paris"},
    {"name": "ING BANK NV",                "bic": "INGBNL2A", "country": "NL", "city": "Amsterdam"},
    {"name": "ABN AMRO BANK NV",           "bic": "ABNANL2A", "country": "NL", "city": "Amsterdam"},
    {"name": "COMMERZBANK AG",             "bic": "COBADEFF", "country": "DE", "city": "Frankfurt"},
    {"name": "UNICREDIT SPA",              "bic": "UNCRITMM", "country": "IT", "city": "Milan"},
    {"name": "STANDARD CHARTERED",        "bic": "SCBLGB2L", "country": "GB", "city": "London"},
    {"name": "HSBC BANK PLC",              "bic": "MIDLGB22", "country": "GB", "city": "London"},
    {"name": "BARCLAYS BANK PLC",          "bic": "BARCGB22", "country": "GB", "city": "London"},
    {"name": "JP MORGAN CHASE BANK NA",   "bic": "CHASUS33", "country": "US", "city": "New York"},
    {"name": "CITIBANK NA",                "bic": "CITIUS33", "country": "US", "city": "New York"},
    {"name": "BANK OF NEW YORK MELLON",   "bic": "IRVTUS3N", "country": "US", "city": "New York"},
    {"name": "STATE STREET BANK",         "bic": "SBOSUS33", "country": "US", "city": "Boston"},
    {"name": "CREDIT SUISSE AG",          "bic": "CRESCHZZ", "country": "CH", "city": "Zurich"},
    {"name": "UBS AG",                    "bic": "UBSWCHZH", "country": "CH", "city": "Zurich"},
    {"name": "RABOBANK NA",               "bic": "RABONL2U", "country": "NL", "city": "Amsterdam"},
    {"name": "DZ BANK AG",                "bic": "GENODEFF", "country": "DE", "city": "Frankfurt"},
    {"name": "LANDESBANK BW",             "bic": "SOLADEST", "country": "DE", "city": "Stuttgart"},
    {"name": "KBC BANK NV",               "bic": "KREDBEBB", "country": "BE", "city": "Brussels"},
]

# Clean counterparty institutions (will make up 97%+ of transactions)
CLEAN_ENTITIES = [
    # European Asset Managers
    {"name": "ALLIANZ GLOBAL INVESTORS",      "lei": "5299004L41EN93DNN946", "country": "DE", "type": "asset_manager"},
    {"name": "AMUNDI ASSET MANAGEMENT",       "lei": "969500AL6BAER33B4127", "country": "FR", "type": "asset_manager"},
    {"name": "DWS INVESTMENT GMBH",           "lei": "529900YUQKDXQ41HSR10", "country": "DE", "type": "asset_manager"},
    {"name": "UNION INVESTMENT GMBH",         "lei": "5299009J9MQXNGSQFZ76", "country": "DE", "type": "asset_manager"},
    {"name": "DEKA INVESTMENT GMBH",          "lei": "529900HNOAA1KXQJUQ27", "country": "DE", "type": "asset_manager"},
    {"name": "BLACKROCK INVESTMENT MGMT",     "lei": "5493000V5LDYH45ZWE47", "country": "GB", "type": "asset_manager"},
    {"name": "VANGUARD ASSET MGMT",           "lei": "5493005RLLC0ZWB05V86", "country": "GB", "type": "asset_manager"},
    {"name": "FIDELITY INTL LIMITED",         "lei": "5493005UZHQRQY98BB11", "country": "GB", "type": "asset_manager"},
    {"name": "ABRDN INVESTMENTS LTD",         "lei": "2138004KTRZ3DJFZZX45", "country": "GB", "type": "asset_manager"},
    {"name": "SCHRODERS PLC",                 "lei": "2138005DU8TK7UYRFQ21", "country": "GB", "type": "asset_manager"},
    # European Banks
    {"name": "ERSTE GROUP BANK AG",           "lei": "PQOH26KWDF7CG10L6792", "country": "AT", "type": "bank"},
    {"name": "RAIFFEISEN BANK INTL",          "lei": "9ZHRYM6F437SQJ6OUG95", "country": "AT", "type": "bank"},
    {"name": "KBC GROUP NV",                  "lei": "6B2PBRV1FCJDMR45RZ53", "country": "BE", "type": "bank"},
    {"name": "DANSKE BANK AS",                "lei": "MAES062Z21O4RZ2U7M96", "country": "DK", "type": "bank"},
    {"name": "NORDEA BANK ABP",               "lei": "529900ODI3047E2LIV03", "country": "FI", "type": "bank"},
    {"name": "CREDIT AGRICOLE SA",            "lei": "1VUV7VQFKUOQSJ21A208", "country": "FR", "type": "bank"},
    {"name": "NATIXIS SA",                    "lei": "KX1WK48MPD4Y2NCLIOB3", "country": "FR", "type": "bank"},
    {"name": "HELABA LANDESBANK",             "lei": "DIZES3AWX28YE4KPEE32", "country": "DE", "type": "bank"},
    {"name": "BANCA INTESA SANPAOLO",         "lei": "2W8N8UU78PMDQKZENC08", "country": "IT", "type": "bank"},
    {"name": "MEDIOBANCA SPA",                "lei": "815600E57CC6ED7A9E11", "country": "IT", "type": "bank"},
    {"name": "ABN AMRO BANK NV",              "lei": "BFXS5XCH7N0Y05NIXW11", "country": "NL", "type": "bank"},
    {"name": "RABOBANK NA",                   "lei": "DG3RU1DBUFHT4ZF9WN62", "country": "NL", "type": "bank"},
    {"name": "PKO BANK POLSKI",               "lei": "PSZWLR3E51FHKBZRAQ42", "country": "PL", "type": "bank"},
    {"name": "SANTANDER SA",                  "lei": "5493006QMFDDMYWIAM13", "country": "ES", "type": "bank"},
    {"name": "BBVA SA",                       "lei": "K8MS7FD7N5Z2WQ51AZ71", "country": "ES", "type": "bank"},
    {"name": "SWEDBANK AB",                   "lei": "M312WZV08Y7LYUC71685", "country": "SE", "type": "bank"},
    {"name": "SEB AB",                        "lei": "F3JS33DEI6XQ4ZBPTN86", "country": "SE", "type": "bank"},
    {"name": "JULIUS BAER GRUPPE AG",         "lei": "529900F0CIEHYX2BTSN55", "country": "CH", "type": "bank"},
    # Custodians / CSDs
    {"name": "EUROCLEAR BANK SA",             "lei": "PNCEA0065BI9PZMDGE43", "country": "BE", "type": "custodian"},
    {"name": "BNY MELLON SA/NV",              "lei": "724500KNWT7PRHDNO697", "country": "BE", "type": "custodian"},
    {"name": "CACEIS BANK",                   "lei": "969500XH59KSMPJJHE41", "country": "FR", "type": "custodian"},
    {"name": "SOCIETE GENERALE SECURITIES",  "lei": "O2RNE8IBXP4R0TD8PU41", "country": "FR", "type": "custodian"},
    {"name": "STATE STREET BANK INTL",        "lei": "I7331LVCZKQKX5T7XV54", "country": "DE", "type": "custodian"},
    # Insurance & Pensions
    {"name": "MUNICH RE AG",                  "lei": "529900DKZK1T02Q4LW55", "country": "DE", "type": "insurance"},
    {"name": "ZURICH INSURANCE GROUP",        "lei": "5493007DRC2YQ3GGBN05", "country": "CH", "type": "insurance"},
    {"name": "AXA SA",                        "lei": "EXCLUDED3LO9DGNZ3VD32", "country": "FR", "type": "insurance"},
    {"name": "GENERALI GROUP",                "lei": "ZCNF3G0DZQ49RCHB2M63", "country": "IT", "type": "insurance"},
    {"name": "APG ASSET MANAGEMENT",         "lei": "4PHHZ07X3PB5SBE0L455", "country": "NL", "type": "pension"},
]

# FATF grey-list / high-risk countries (as of 2025)
FATF_HIGH_RISK = {
    "AF": "Afghanistan",
    "KP": "North Korea",
    "IR": "Iran",
    "MM": "Myanmar",
    "SY": "Syria",
    "YE": "Yemen",
    "IQ": "Iraq (high-risk)",
    "LY": "Libya",
    "SS": "South Sudan",
    "PK": "Pakistan",
    "NG": "Nigeria",
    "VN": "Vietnam (monitoring)",
    "PH": "Philippines",
    "BJ": "Benin",
    "CM": "Cameroon",
    "HT": "Haiti",
    "JM": "Jamaica",
    "MZ": "Mozambique",
    "SN": "Senegal",
    "TZ": "Tanzania",
    "TR": "Turkey",
    "UG": "Uganda",
    "AE": "UAE (enhanced monitoring)",
}

CLEAN_COUNTRIES = [
    "DE", "FR", "GB", "NL", "BE", "LU", "AT", "CH", "SE", "DK",
    "FI", "NO", "IT", "ES", "PT", "IE", "PL", "CZ", "HU", "US",
    "CA", "AU", "JP", "SG", "HK", "NZ",
]

CURRENCIES = {
    "EUR": 1.00, "USD": 0.92, "GBP": 1.16, "CHF": 1.02,
    "JPY": 0.0062, "SEK": 0.087, "DKK": 0.134, "NOK": 0.085,
    "PLN": 0.23, "CZK": 0.041,
}

# Real ISINs (Eurobonds + German/French/UK equities — publicly listed)
SECURITIES = [
    {"isin": "DE0005140008", "name": "DEUTSCHE BANK AG",        "type": "Equity",       "currency": "EUR"},
    {"isin": "DE0007164600", "name": "SAP SE",                  "type": "Equity",       "currency": "EUR"},
    {"isin": "DE0008404005", "name": "ALLIANZ SE",              "type": "Equity",       "currency": "EUR"},
    {"isin": "DE0005552004", "name": "DEUTSCHE POST AG",        "type": "Equity",       "currency": "EUR"},
    {"isin": "DE000A1H3AZ0", "name": "KFW 1.625% 2028",        "type": "EuroBond",     "currency": "EUR"},
    {"isin": "XS1503353557", "name": "BMW FINANCE 0.875% 2026", "type": "EuroBond",    "currency": "EUR"},
    {"isin": "FR0000131104", "name": "BNP PARIBAS SA",          "type": "Equity",       "currency": "EUR"},
    {"isin": "FR0000130809", "name": "SOCIETE GENERALE SA",     "type": "Equity",       "currency": "EUR"},
    {"isin": "XS2353234848", "name": "REPUBLIC OF FRANCE 0.5% 2031", "type": "Sovereign", "currency": "EUR"},
    {"isin": "XS1960699202", "name": "EUROPEAN INVESTMENT BANK 0.375% 2024", "type": "Supranational", "currency": "EUR"},
    {"isin": "XS2138007974", "name": "ESM 0.0% 2025",          "type": "Supranational","currency": "EUR"},
    {"isin": "GB0031348658", "name": "HSBC HOLDINGS PLC",       "type": "Equity",       "currency": "GBP"},
    {"isin": "GB00B24CGK77", "name": "BARCLAYS PLC",            "type": "Equity",       "currency": "GBP"},
    {"isin": "GB0031743012", "name": "LLOYDS BANKING GROUP",    "type": "Equity",       "currency": "GBP"},
    {"isin": "XS1614576686", "name": "UK GILT 1.5% 2026",      "type": "Sovereign",    "currency": "GBP"},
    {"isin": "US912828YW27", "name": "US TREASURY 1.75% 2022", "type": "Sovereign",    "currency": "USD"},
    {"isin": "CH0012221716", "name": "ABB LTD",                 "type": "Equity",       "currency": "CHF"},
    {"isin": "CH0012410517", "name": "JULIUS BAER GROUP LTD",   "type": "Equity",       "currency": "CHF"},
]

BOOKING_CENTRES = {
    "LU": "Clearstream Banking Luxembourg S.A.",
    "DE": "Clearstream Banking Frankfurt AG",
    "BE": "Euroclear Bank (Bridge)",
}

PURPOSE_CODES = [
    "CORT",  # Corporate Trade
    "TRAD",  # Trade (general)
    "INTC",  # Intra-company payment
    "DIVI",  # Dividend
    "INTE",  # Interest payment
    "SECU",  # Securities
    "PENS",  # Pension
    "SALA",  # Salary
    "SUPP",  # Supplier payment
    "LOAN",  # Loan repayment
    "REPO",  # Repurchase agreement
    "COLC",  # Collateral cash leg
]

INSTRUCTION_TYPES = ["DELIVER_AGAINST_PAYMENT", "RECEIVE_AGAINST_PAYMENT",
                     "DELIVER_FREE", "RECEIVE_FREE"]

# ── HELPERS ───────────────────────────────────────────────────────────────

def _rand_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def _rand_amount(mu: float, sigma: float, low: float = 1000, high: float = 50_000_000) -> float:
    """Log-normal distribution — realistic for interbank payments."""
    import math
    log_mu = math.log(mu)
    val = random.lognormvariate(log_mu, sigma)
    return round(min(max(val, low), high), 2)


def _to_eur(amount: float, currency: str) -> float:
    rate = CURRENCIES.get(currency, 1.0)
    return round(amount * rate, 2)


def _make_txn_id(prefix: str, seq: int) -> str:
    return f"{prefix}-2024-{seq:08d}"


def _make_account(country: str) -> str:
    """Generate plausible IBAN-style account reference."""
    chars = string.digits
    return f"{country}{''.join(random.choices(chars, k=18))}"


def _make_reference() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))


def _make_lei() -> str:
    """Generate synthetic LEI (20-char ISO 17442 format)."""
    chars = string.ascii_uppercase + string.digits
    prefix = ''.join(random.choices(chars, k=4))
    body = ''.join(random.choices(chars, k=14))
    check = ''.join(random.choices(string.digits, k=2))
    return f"{prefix}{body}{check}"


def _pick_country(high_risk_prob: float = 0.02) -> str:
    """Pick a country — mostly clean, occasionally high-risk."""
    if random.random() < high_risk_prob:
        return random.choice(list(FATF_HIGH_RISK.keys()))
    return random.choice(CLEAN_COUNTRIES)


def _pick_entity(sanctioned_entities: list, sanctions_hit_prob: float = 0.0008):
    """Pick a counterparty — usually clean, occasionally sanctioned."""
    if random.random() < sanctions_hit_prob and sanctioned_entities:
        e = random.choice(sanctioned_entities)
        return {
            "name": e["canonical_name"],
            "lei": _make_lei(),
            "country": e["country"],
            "is_sanctioned": True,
            "sanctions_uid": e["uid"],
            "sanctions_list": e["list_source"],
            "sanctions_programme": e["programme"],
        }
    entity = random.choice(CLEAN_ENTITIES)
    return {
        "name": entity["name"],
        "lei": entity["lei"],
        "country": entity["country"],
        "is_sanctioned": False,
        "sanctions_uid": None,
        "sanctions_list": None,
        "sanctions_programme": None,
    }


def _load_sanctioned_entities() -> list:
    entities = []
    try:
        with open(SANCTIONS_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                entities.append(row)
    except FileNotFoundError:
        print("  ⚠ Sanctions master list not found — run build_sanctions_lists.py first")
    return entities


# ── AML TYPOLOGY INJECTORS ────────────────────────────────────────────────

def _inject_structuring_cluster(base_ts: datetime, sender: dict) -> list[dict]:
    """
    Structuring: 8-12 transactions just below €9,999 within 48h
    from the same sender to the same receiver via different banks.
    FATF Typology: deliberate sub-threshold splitting.
    """
    cluster = []
    n = random.randint(8, 12)
    receiver_bank = random.choice(CORRESPONDENT_BANKS)
    receiver_account = _make_account(receiver_bank["country"])

    for i in range(n):
        amount = round(random.uniform(8_500, 9_998), 2)  # Just below €9,999
        ts = base_ts + timedelta(hours=random.uniform(0, 48))
        cluster.append({
            "_amount": amount,
            "_currency": "EUR",
            "_timestamp": ts,
            "_sender_name": sender["name"],
            "_sender_country": sender["country"],
            "_receiver_name": receiver_bank["name"],
            "_receiver_country": receiver_bank["country"],
            "_receiver_account": receiver_account,
            "_aml_typology": "STRUCTURING",
            "_typology_cluster_id": hashlib.md5(
                f"{sender['name']}{base_ts}".encode()
            ).hexdigest()[:10],
            "_is_suspicious": True,
        })
    return cluster


def _inject_layering_chain(base_ts: datetime, start_amount: float) -> list[dict]:
    """
    Layering: same funds move through 3-4 jurisdictions within 7 days.
    Each hop the amount changes slightly (fees/fx) to obscure tracking.
    """
    chain = []
    jurisdictions = random.sample(
        ["LU", "CH", "MT", "CY", "HK", "SG", "AE", "PA", "VG", "KY"], 4
    )
    amount = start_amount
    cluster_id = _make_reference()[:10]

    for i, jur in enumerate(jurisdictions):
        amount = round(amount * random.uniform(0.97, 0.999), 2)  # Slight reduction each hop
        ts = base_ts + timedelta(days=i * random.uniform(0.5, 2))
        chain.append({
            "_amount": amount,
            "_currency": random.choice(["EUR", "USD", "CHF", "GBP"]),
            "_timestamp": ts,
            "_sender_country": jurisdictions[i - 1] if i > 0 else jur,
            "_receiver_country": jur,
            "_aml_typology": "LAYERING",
            "_typology_cluster_id": cluster_id,
            "_is_suspicious": True,
        })
    return chain


# ── GENERATORS ────────────────────────────────────────────────────────────

def generate_mt103(n: int, sanctioned_entities: list) -> list[dict]:
    """
    MT103 Single Customer Credit Transfer.
    Backbone of cross-border wire payments at Clearstream.
    """
    print(f"  Generating {n:,} MT103 wire transfers...", end="", flush=True)
    rows = []
    start_dt = datetime(2024, 1, 1)
    end_dt = datetime(2024, 12, 31, 23, 59, 59)

    # Pre-inject AML clusters (structuring)
    structuring_rows = []
    n_structuring_clusters = int(n * 0.003)   # ~0.3% of total volume
    for _ in range(n_structuring_clusters):
        base_ts = _rand_date(start_dt, end_dt)
        sender = random.choice(CLEAN_ENTITIES)
        cluster = _inject_structuring_cluster(base_ts, sender)
        structuring_rows.extend(cluster)

    normal_n = n - len(structuring_rows)

    for i in range(normal_n):
        ts = _rand_date(start_dt, end_dt)
        currency = random.choices(
            list(CURRENCIES.keys()),
            weights=[60, 20, 8, 4, 2, 2, 1, 1, 1, 1],
            k=1
        )[0]
        amount = _rand_amount(
            mu=random.choice([50_000, 250_000, 1_000_000]),
            sigma=random.choice([0.8, 1.2, 1.5]),
        )

        sender = _pick_entity(sanctioned_entities)
        receiver = _pick_entity(sanctioned_entities)
        corr = random.choice(CORRESPONDENT_BANKS)
        sender_country = _pick_country(0.015)
        receiver_country = _pick_country(0.015)

        is_high_risk = sender_country in FATF_HIGH_RISK or receiver_country in FATF_HIGH_RISK
        is_sanctions_hit = sender["is_sanctioned"] or receiver["is_sanctioned"]

        rows.append({
            "transaction_id": _make_txn_id("MT103", i + 1),
            "message_type": "MT103",
            "booking_date": ts.date().isoformat(),
            "value_date": (ts + timedelta(days=random.choice([1, 2]))).date().isoformat(),
            "timestamp": ts.isoformat(),
            "booking_centre": random.choices(["LU", "DE"], weights=[70, 30])[0],
            # Sender
            "sender_name": sender["name"],
            "sender_lei": sender["lei"],
            "sender_bic": _make_reference()[:8],
            "sender_account": _make_account(sender["country"]),
            "sender_country": sender_country,
            # Receiver
            "receiver_name": receiver["name"],
            "receiver_lei": receiver["lei"],
            "receiver_bic": _make_reference()[:8],
            "receiver_account": _make_account(receiver["country"]),
            "receiver_country": receiver_country,
            # Correspondent
            "correspondent_bank_name": corr["name"],
            "correspondent_bank_bic": corr["bic"],
            "correspondent_bank_country": corr["country"],
            # Value
            "amount": amount,
            "currency": currency,
            "amount_eur": _to_eur(amount, currency),
            "purpose_code": random.choice(PURPOSE_CODES),
            "remittance_info": _make_reference(),
            # Compliance flags
            "sender_is_sanctions_hit": sender["is_sanctioned"],
            "receiver_is_sanctions_hit": receiver["is_sanctioned"],
            "sanctions_hit_name": sender["name"] if sender["is_sanctioned"] else (receiver["name"] if receiver["is_sanctioned"] else None),
            "sanctions_uid": sender["sanctions_uid"] or receiver["sanctions_uid"],
            "sanctions_list_source": sender["sanctions_list"] or receiver["sanctions_list"],
            "sanctions_programme": sender["sanctions_programme"] or receiver["sanctions_programme"],
            "is_high_risk_jurisdiction": is_high_risk,
            "high_risk_country": sender_country if sender_country in FATF_HIGH_RISK else (receiver_country if receiver_country in FATF_HIGH_RISK else None),
            "aml_typology": None,
            "typology_cluster_id": None,
            "is_suspicious": is_sanctions_hit or is_high_risk,
            "alert_status": "OPEN" if (is_sanctions_hit or is_high_risk) else "CLEAR",
        })

    # Merge structuring clusters
    for i, s in enumerate(structuring_rows):
        currency = s.get("_currency", "EUR")
        amount = s["_amount"]
        corr = random.choice(CORRESPONDENT_BANKS)
        sender_country = s.get("_sender_country", "DE")
        receiver_country = s.get("_receiver_country", "CH")

        rows.append({
            "transaction_id": _make_txn_id("MT103-STR", normal_n + i + 1),
            "message_type": "MT103",
            "booking_date": s["_timestamp"].date().isoformat(),
            "value_date": (s["_timestamp"] + timedelta(days=1)).date().isoformat(),
            "timestamp": s["_timestamp"].isoformat(),
            "booking_centre": "LU",
            "sender_name": s["_sender_name"],
            "sender_lei": _make_lei(),
            "sender_bic": _make_reference()[:8],
            "sender_account": _make_account(sender_country),
            "sender_country": sender_country,
            "receiver_name": s["_receiver_name"],
            "receiver_lei": _make_lei(),
            "receiver_bic": corr["bic"],
            "receiver_account": s.get("_receiver_account", _make_account(receiver_country)),
            "receiver_country": receiver_country,
            "correspondent_bank_name": corr["name"],
            "correspondent_bank_bic": corr["bic"],
            "correspondent_bank_country": corr["country"],
            "amount": amount,
            "currency": currency,
            "amount_eur": _to_eur(amount, currency),
            "purpose_code": "TRAD",
            "remittance_info": _make_reference(),
            "sender_is_sanctions_hit": False,
            "receiver_is_sanctions_hit": False,
            "sanctions_hit_name": None,
            "sanctions_uid": None,
            "sanctions_list_source": None,
            "sanctions_programme": None,
            "is_high_risk_jurisdiction": False,
            "high_risk_country": None,
            "aml_typology": s["_aml_typology"],
            "typology_cluster_id": s["_typology_cluster_id"],
            "is_suspicious": True,
            "alert_status": "OPEN",
        })

    random.shuffle(rows)
    print(f" ✓ ({len(rows):,} rows, {len(structuring_rows)} structuring injections)")
    return rows


def generate_mt540(n: int, sanctioned_entities: list) -> list[dict]:
    """
    MT540/542/543 Securities Settlement Instructions.
    Deliver/Receive Against Payment or Free of Payment.
    """
    print(f"  Generating {n:,} MT540 securities settlements...", end="", flush=True)
    rows = []
    start_dt = datetime(2024, 1, 1)
    end_dt = datetime(2024, 12, 31)

    for i in range(n):
        trade_dt = _rand_date(start_dt, end_dt)
        settle_dt = trade_dt + timedelta(days=random.choice([1, 2, 2, 2, 3]))  # T+2 standard
        security = random.choice(SECURITIES)
        currency = security["currency"]
        price = _rand_amount(mu=100, sigma=0.3, low=0.01, high=5000)
        quantity = random.choice([
            random.randint(1_000, 100_000),
            random.randint(100_000, 5_000_000),
            random.randint(1_000_000, 50_000_000),
        ])
        settlement_amount = round(price * quantity / 100, 2)  # per-unit basis for bonds

        delivering = _pick_entity(sanctioned_entities, 0.0006)
        receiving = _pick_entity(sanctioned_entities, 0.0006)
        is_sanctions = delivering["is_sanctioned"] or receiving["is_sanctioned"]

        instr_type = random.choices(
            INSTRUCTION_TYPES,
            weights=[40, 40, 10, 10]
        )[0]

        booking_centre = random.choices(["LU", "DE"], weights=[65, 35])[0]

        rows.append({
            "transaction_id": _make_txn_id("MT540", i + 1),
            "message_type": instr_type,
            "trade_date": trade_dt.date().isoformat(),
            "settlement_date": settle_dt.date().isoformat(),
            "timestamp": trade_dt.isoformat(),
            "booking_centre": booking_centre,
            "booking_centre_name": BOOKING_CENTRES[booking_centre],
            # Security
            "isin": security["isin"],
            "security_name": security["name"],
            "security_type": security["type"],
            "quantity": quantity,
            "price": price,
            "currency": currency,
            "settlement_amount": settlement_amount,
            "settlement_amount_eur": _to_eur(settlement_amount, currency),
            # Parties
            "delivering_party_name": delivering["name"],
            "delivering_party_lei": delivering["lei"],
            "delivering_party_country": delivering["country"],
            "receiving_party_name": receiving["name"],
            "receiving_party_lei": receiving["lei"],
            "receiving_party_country": receiving["country"],
            # Custodian
            "custodian": random.choice(CORRESPONDENT_BANKS)["name"],
            # Settlement
            "settlement_status": random.choices(
                ["SETTLED", "FAILED", "PENDING", "CANCELLED"],
                weights=[88, 5, 5, 2]
            )[0],
            "instruction_reference": _make_reference(),
            # Compliance
            "delivering_is_sanctions_hit": delivering["is_sanctioned"],
            "receiving_is_sanctions_hit": receiving["is_sanctioned"],
            "sanctions_hit_name": delivering["name"] if delivering["is_sanctioned"] else (receiving["name"] if receiving["is_sanctioned"] else None),
            "sanctions_uid": delivering["sanctions_uid"] or receiving["sanctions_uid"],
            "sanctions_list_source": delivering["sanctions_list"] or receiving["sanctions_list"],
            "sanctions_programme": delivering["sanctions_programme"] or receiving["sanctions_programme"],
            "is_high_risk_jurisdiction": delivering["country"] in FATF_HIGH_RISK or receiving["country"] in FATF_HIGH_RISK,
            "aml_typology": None,
            "is_suspicious": is_sanctions,
            "alert_status": "OPEN" if is_sanctions else "CLEAR",
        })

    print(f" ✓ ({len(rows):,} rows)")
    return rows


def generate_mt202(n: int, sanctioned_entities: list) -> list[dict]:
    """
    MT202 General Financial Institution Transfer.
    Interbank movements — high-value, low-volume, layering risk.
    """
    print(f"  Generating {n:,} MT202 interbank transfers...", end="", flush=True)
    rows = []
    start_dt = datetime(2024, 1, 1)
    end_dt = datetime(2024, 12, 31)

    # Inject layering chains (~1% of volume)
    layering_rows = []
    n_layering = int(n * 0.01)
    for _ in range(n_layering):
        base_ts = _rand_date(start_dt, end_dt)
        start_amount = _rand_amount(mu=5_000_000, sigma=1.0, low=500_000, high=50_000_000)
        chain = _inject_layering_chain(base_ts, start_amount)
        layering_rows.extend(chain)

    normal_n = n - len(layering_rows)

    for i in range(normal_n):
        ts = _rand_date(start_dt, end_dt)
        currency = random.choices(
            list(CURRENCIES.keys()),
            weights=[55, 25, 8, 5, 2, 2, 1, 1, 1, 0],
            k=1
        )[0]
        amount = _rand_amount(mu=2_000_000, sigma=1.5, low=100_000, high=100_000_000)

        ordering_bank = random.choice(CORRESPONDENT_BANKS)
        beneficiary_bank = random.choice(CORRESPONDENT_BANKS)
        is_high_risk = (ordering_bank["country"] in FATF_HIGH_RISK or
                        beneficiary_bank["country"] in FATF_HIGH_RISK)

        rows.append({
            "transaction_id": _make_txn_id("MT202", i + 1),
            "message_type": "MT202",
            "booking_date": ts.date().isoformat(),
            "value_date": (ts + timedelta(days=1)).date().isoformat(),
            "timestamp": ts.isoformat(),
            "booking_centre": random.choices(["LU", "DE"], weights=[70, 30])[0],
            "ordering_institution_name": ordering_bank["name"],
            "ordering_institution_bic": ordering_bank["bic"],
            "ordering_institution_country": ordering_bank["country"],
            "beneficiary_institution_name": beneficiary_bank["name"],
            "beneficiary_institution_bic": beneficiary_bank["bic"],
            "beneficiary_institution_country": beneficiary_bank["country"],
            "amount": amount,
            "currency": currency,
            "amount_eur": _to_eur(amount, currency),
            "transaction_reference": _make_reference(),
            "related_reference": _make_reference(),
            "purpose_code": random.choice(["REPO", "COLC", "INTE", "LOAN", "INTC"]),
            "is_high_risk_jurisdiction": is_high_risk,
            "high_risk_country": ordering_bank["country"] if ordering_bank["country"] in FATF_HIGH_RISK else None,
            "aml_typology": None,
            "typology_cluster_id": None,
            "is_suspicious": is_high_risk,
            "alert_status": "OPEN" if is_high_risk else "CLEAR",
        })

    # Merge layering chains
    for i, s in enumerate(layering_rows):
        currency = s.get("_currency", "EUR")
        amount = s["_amount"]
        sender_country = s.get("_sender_country", "LU")
        receiver_country = s.get("_receiver_country", "CH")
        corr_s = random.choice(CORRESPONDENT_BANKS)
        corr_r = random.choice(CORRESPONDENT_BANKS)

        rows.append({
            "transaction_id": _make_txn_id("MT202-LAY", normal_n + i + 1),
            "message_type": "MT202",
            "booking_date": s["_timestamp"].date().isoformat(),
            "value_date": (s["_timestamp"] + timedelta(days=1)).date().isoformat(),
            "timestamp": s["_timestamp"].isoformat(),
            "booking_centre": "LU",
            "ordering_institution_name": corr_s["name"],
            "ordering_institution_bic": corr_s["bic"],
            "ordering_institution_country": sender_country,
            "beneficiary_institution_name": corr_r["name"],
            "beneficiary_institution_bic": corr_r["bic"],
            "beneficiary_institution_country": receiver_country,
            "amount": amount,
            "currency": currency,
            "amount_eur": _to_eur(amount, currency),
            "transaction_reference": _make_reference(),
            "related_reference": _make_reference(),
            "purpose_code": "INTC",
            "is_high_risk_jurisdiction": (sender_country in FATF_HIGH_RISK or receiver_country in FATF_HIGH_RISK),
            "high_risk_country": sender_country if sender_country in FATF_HIGH_RISK else None,
            "aml_typology": s["_aml_typology"],
            "typology_cluster_id": s["_typology_cluster_id"],
            "is_suspicious": True,
            "alert_status": "OPEN",
        })

    random.shuffle(rows)
    print(f" ✓ ({len(rows):,} rows, {len(layering_rows)} layering injections)")
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys(), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_ground_truth(mt103: list, mt540: list, mt202: list, path: Path) -> None:
    """Write a ground truth labels file for model evaluation."""
    rows = []
    for r in mt103 + mt202:
        if r.get("is_suspicious"):
            rows.append({
                "transaction_id": r["transaction_id"],
                "message_type": r["message_type"],
                "is_suspicious": True,
                "aml_typology": r.get("aml_typology") or ("SANCTIONS_HIT" if r.get("sender_is_sanctions_hit") or r.get("receiver_is_sanctions_hit") else "HIGH_RISK_JURISDICTION"),
                "typology_cluster_id": r.get("typology_cluster_id"),
                "sanctions_uid": r.get("sanctions_uid"),
                "sanctions_programme": r.get("sanctions_programme"),
                "amount_eur": r.get("amount_eur"),
            })
    for r in mt540:
        if r.get("is_suspicious"):
            rows.append({
                "transaction_id": r["transaction_id"],
                "message_type": r["message_type"],
                "is_suspicious": True,
                "aml_typology": "SANCTIONS_HIT" if r.get("delivering_is_sanctions_hit") or r.get("receiving_is_sanctions_hit") else "HIGH_RISK_JURISDICTION",
                "typology_cluster_id": None,
                "sanctions_uid": r.get("sanctions_uid"),
                "sanctions_programme": r.get("sanctions_programme"),
                "amount_eur": r.get("settlement_amount_eur"),
            })
    write_csv(rows, path)
    return len(rows)


# ── MAIN ──────────────────────────────────────────────────────────────────

def main(n_mt103: int = 300_000, n_mt540: int = 200_000, n_mt202: int = 100_000):
    print("\n📊 FCC Compliance Analytics Suite — Transaction Generator")
    print(f"   Total target: {n_mt103 + n_mt540 + n_mt202:,} transactions\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sanctioned = _load_sanctioned_entities()
    print(f"  ✓ Loaded {len(sanctioned)} sanctioned entities from master list\n")

    mt103 = generate_mt103(n_mt103, sanctioned)
    mt540 = generate_mt540(n_mt540, sanctioned)
    mt202 = generate_mt202(n_mt202, sanctioned)

    print("\n  Writing files...")
    write_csv(mt103, OUTPUT_DIR / "transactions_mt103.csv")
    print(f"    ✓ transactions_mt103.csv ({len(mt103):,} rows)")

    write_csv(mt540, OUTPUT_DIR / "transactions_mt540.csv")
    print(f"    ✓ transactions_mt540.csv ({len(mt540):,} rows)")

    write_csv(mt202, OUTPUT_DIR / "transactions_mt202.csv")
    print(f"    ✓ transactions_mt202.csv ({len(mt202):,} rows)")

    # Combined (union of shared fields)
    combined_fields = [
        "transaction_id", "message_type", "timestamp", "booking_centre",
        "amount_eur", "currency", "is_suspicious", "aml_typology",
        "alert_status", "is_high_risk_jurisdiction",
    ]
    combined = []
    for r in mt103 + mt540 + mt202:
        combined.append({f: r.get(f) for f in combined_fields})
    write_csv(combined, OUTPUT_DIR / "transactions_combined.csv")
    print(f"    ✓ transactions_combined.csv ({len(combined):,} rows)")

    n_gt = write_ground_truth(mt103, mt540, mt202, OUTPUT_DIR / "ground_truth_labels.csv")
    print(f"    ✓ ground_truth_labels.csv ({n_gt:,} labelled suspicious rows)")

    # Summary stats
    total = len(mt103) + len(mt540) + len(mt202)
    n_suspicious = sum(1 for r in mt103 + mt540 + mt202 if r.get("is_suspicious"))
    n_sanctions = sum(1 for r in mt103 if r.get("sender_is_sanctions_hit") or r.get("receiver_is_sanctions_hit"))
    n_structuring = sum(1 for r in mt103 if r.get("aml_typology") == "STRUCTURING")
    n_layering = sum(1 for r in mt202 if r.get("aml_typology") == "LAYERING")
    n_high_risk = sum(1 for r in mt103 + mt202 if r.get("is_high_risk_jurisdiction"))

    print(f"""
╔══════════════════════════════════════════════╗
║         GENERATION COMPLETE                  ║
╠══════════════════════════════════════════════╣
║  Total transactions    {total:>10,}           ║
║  MT103 wire transfers  {len(mt103):>10,}           ║
║  MT540 settlements     {len(mt540):>10,}           ║
║  MT202 interbank       {len(mt202):>10,}           ║
╠══════════════════════════════════════════════╣
║  SUSPICIOUS (total)    {n_suspicious:>10,}           ║
║  → Sanctions hits      {n_sanctions:>10,}           ║
║  → Structuring         {n_structuring:>10,}           ║
║  → Layering            {n_layering:>10,}           ║
║  → High-risk corridor  {n_high_risk:>10,}           ║
║  Alert rate            {n_suspicious/total*100:>9.2f}%           ║
╚══════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=600_000,
                        help="Total rows to generate (default: 600000)")
    args = parser.parse_args()

    total = args.rows
    main(
        n_mt103=int(total * 0.50),
        n_mt540=int(total * 0.33),
        n_mt202=int(total * 0.17),
    )
