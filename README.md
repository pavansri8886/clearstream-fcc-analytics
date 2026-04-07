# Clearstream FCC Analytics Suite

**Financial Crime Compliance analytics replicating real-world AML workflows at a post-trade financial institution.**

Built to reflect the work of a compliance team at **Clearstream Banking S.A., Luxembourg** — one of the world's two International Central Securities Depositories (ICSDs), regulated by the CSSF and subject to OFAC, UN, and EU sanctions obligations.

---

## What This Project Does

Screens 600,000 synthetic Clearstream transactions for financial crime across four FATF typologies and three sanctions lists, then produces a management-ready Excel compliance report.

---

## Results

| Metric | Value |
|---|---|
| Transactions Screened | 600,000 |
| Sanctions Hits | 443 |
| Structuring Cases | 8,984 |
| High-Risk Corridor Alerts | 9,186 |
| Alert Rate | 3.71% |
| Tests Passing | 108 / 108 |

---

## How It Works

### 1. Sanctions Screening
Every transaction is checked against three real public watchlists:

| List | Issuer |
|---|---|
| OFAC SDN List | US Treasury |
| UN Consolidated List | UN Security Council |
| EU Financial Sanctions Files | European Commission |

Matching uses **exact lookup** for speed, with **fuzzy name matching** (rapidfuzz) to catch typos and aliases — e.g. `GAZPROM BANK` matches `GAZPROMBANK` at 95% confidence.

### 2. AML Detection (4 FATF Typologies)

| Typology | Rule |
|---|---|
| **Structuring** | 3+ transactions between €5,000–€9,999 from the same sender within 72 hours |
| **Velocity Abuse** | 20+ payments from the same entity within 1 hour |
| **Large Transaction** | Single transfer above €1,000,000 |
| **High-Risk Corridor** | Any transaction involving a FATF grey-list country |

### 3. Excel Compliance Report
`reports/fcc_compliance_report.xlsx`

| Sheet | Contents |
|---|---|
| Summary | KPI dashboard — alert counts, severity breakdown, SAR candidates |
| Alerts | Top 1,000 HIGH severity alerts sorted by EUR exposure |
| Sanctions | Full list of sanctions matches with entity, programme, and match score |

---

## Transaction Types

| SWIFT Type | Volume | Description |
|---|---|---|
| MT103 | 300,000 | Cross-border customer wire transfers |
| MT202 | 102,000 | Interbank fund transfers |
| MT540 | 198,000 | Securities settlements (DVP/RVP) |

---

## Regulatory Framework

| Regulation | Requirement |
|---|---|
| CSSF Regulation 12-02 | AML/CFT framework for Luxembourg entities |
| EU AML Package (AMLR + AMLD6) | Enhanced CDD and harmonised STR rules |
| AMLA | New EU AML Authority — direct supervision from July 2026 |
| FATF Recommendation 16 | Travel Rule for cross-border payment data |
| Luxembourg Law 12 Nov 2004 | STR filing obligations via goAML |

---

## Project Structure

```
clearstream-fcc-analytics/
│
├── src/
│   ├── config.py          ← Loads settings.yaml once, shared across all modules
│   ├── pipeline.py        ← Entry point — reads transactions, runs all detectors
│   ├── screener.py        ← Sanctions matching (exact + fuzzy)
│   ├── detectors.py       ← AML rule engines (4 typologies)
│   ├── schema.py          ← AlertRecord data model and field definitions
│   └── reports.py         ← Generates the Excel compliance report
│
├── config/
│   └── settings.yaml      ← All thresholds, paths, and FATF country list
│
├── data/
│   └── raw/sanctions/     ← OFAC, UN, and EU sanctions reference lists
│
├── reports/
│   └── fcc_compliance_report.xlsx
│
└── tests/                 ← 108 unit tests
```

---

## Run

```bash
python src/pipeline.py    # screens all transactions → data/processed/alerts.csv
python src/reports.py     # builds Excel report    → reports/fcc_compliance_report.xlsx
```
