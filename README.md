# 🏦 Clearstream FCC Analytics Suite

> **Financial Crime Compliance analytics built to mirror the real-world reporting workflows of a post-trade financial institution.**

This project replicates the core AML monitoring and sanctions screening work of a compliance team at **Clearstream Banking S.A., Luxembourg** — one of the world's two International Central Securities Depositories (ICSDs), regulated by the CSSF and subject to direct OFAC, UN, and EU sanctions obligations.

---

## 📊 What This Project Delivers

A production-ready Excel compliance report — the kind of document a compliance team actually hands to management.

### 📋 FCC Compliance Report
`reports/fcc_compliance_report.xlsx`

A full-year compliance dashboard built from screening 600,000 Clearstream-style transactions.

| Sheet | Contents |
|---|---|
| 🎯 Summary | KPI cards — transactions screened, alert rate, sanctions hits, SAR candidates |
| 📄 Alerts | Top 1,000 HIGH severity alerts sorted by exposure |
| 🚨 Sanctions | Every match against OFAC, UN, and EU sanctions lists |

---

## 🔍 What Was Analysed

**600,000 synthetic transactions** mirroring real Clearstream SWIFT message types:

| Message Type | Volume | Description |
|---|---|---|
| MT103 | 300,000 | Cross-border customer wire transfers |
| MT540 | 198,000 | Securities settlements (ISIN, LEI, DVP/RVP) |
| MT202 | 102,000 | Interbank fund transfers |

**Screened against three real public sanctions watchlists:**

| List | Source | Entities |
|---|---|---|
| OFAC SDN List | US Treasury | Iran, Russia, DPRK, Belarus, Venezuela |
| UN Consolidated List | UN Security Council | Al-Qaeda, ISIS, DPRK proliferators |
| EU Financial Sanctions Files | European Commission | Russia, Iran, Belarus, Syria |

**Four FATF typologies detected:**

| 🔴 Typology | What It Looks Like |
|---|---|
| Structuring | Multiple transactions just below €10,000 from the same sender within 72 hours |
| Velocity Abuse | 20+ payments from the same entity within a single hour |
| Large Transactions | Single transfers above €1,000,000 (MT103 only) |
| High-Risk Corridors | Any transaction involving a FATF grey-list jurisdiction |

---

## 📌 Key Results

| Metric | Result |
|---|---|
| 💼 Transactions Screened | 600,000 |
| 🚨 Sanctions Hits | 443 across OFAC, UN & EU lists |
| 🔴 Structuring Cases | 8,984 |
| 🌍 High-Risk Corridors | 9,186 |
| 📊 Alert Rate | 3.71% |
| ✅ Tests Passing | 108 / 108 |

---

## 🚀 Run Order

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the AML pipeline (~2 minutes)
python src/pipeline.py

# 3. Generate the Excel compliance report
python src/reports.py
```

---

## ⚖️ Regulatory Framework

Every element of this project was built with reference to Clearstream's actual compliance obligations:

| Regulation | What It Requires |
|---|---|
| **CSSF Regulation 12-02** | AML/CFT framework for Luxembourg regulated entities |
| **EU AML Package** (AMLR + AMLD6) | Enhanced CDD, beneficial ownership registers, harmonised STR rules |
| **AMLA** | New EU Anti-Money Laundering Authority — direct supervision from July 2026 |
| **FATF Recommendation 16** | Travel Rule for cross-border payment data — updated June 2025 |
| **Luxembourg Law 12 Nov 2004** | STR/SAR filing obligations to CRF via goAML platform |

---

## 🛠️ Skills Demonstrated

| Skill | How |
|---|---|
| **Compliance Knowledge** | AML typologies, sanctions screening, SAR flagging, CSSF/FATF/AMLA regulatory framework |
| **Data Analysis** | 600k transactions across 3 data sources, rule-based detection, KPI aggregation |
| **Python + pandas** | Automated pipeline, vectorised detection, 108 unit tests |
| **MS Excel** | Multi-sheet workbooks with conditional formatting and severity colour-coding |

---

## 📁 Project Structure

```
clearstream-fcc-analytics/
├── 📊 reports/                     ← Excel compliance report (open this first)
├── ⚙️  src/
│   ├── config.py                   ← Loads settings.yaml once
│   ├── pipeline.py                 ← Main entry point — screens all transactions
│   ├── screener.py                 ← Sanctions matching (exact + fuzzy)
│   ├── detectors.py                ← AML rule engines (4 typologies)
│   ├── schema.py                   ← AlertRecord data model
│   └── reports.py                  ← Generates Excel compliance report
├── ⚙️  config/
│   └── settings.yaml               ← All thresholds and paths — fully configurable
├── 📂 data/
│   └── raw/sanctions/              ← OFAC, UN, EU reference lists
└── ✅ tests/                        ← 108 unit tests — all passing
```

---

*Built to demonstrate end-to-end financial crime compliance analytics — from raw transaction screening through AML typology detection, sanctions matching, and management-ready Excel reporting.*
