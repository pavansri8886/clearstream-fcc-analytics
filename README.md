# 🏦 Clearstream FCC Analytics Suite

> **Financial Crime Compliance analytics built to mirror the real-world reporting workflows of a post-trade financial institution.**

This project replicates the core AML monitoring, sanctions screening, and PMO reporting work of a compliance team at **Clearstream Banking S.A., Luxembourg** — one of the world's two International Central Securities Depositories (ICSDs), regulated by the CSSF and subject to direct OFAC, UN, and EU sanctions obligations.

---

## 📊 What This Project Delivers

Three production-ready Excel workbooks — the kind of documents a compliance team actually hands to management.

---

### 📋 1. FCC Compliance Report
`reports/fcc_compliance_report.xlsx`

A full-year compliance dashboard built from screening 600,000 Clearstream-style transactions.

| Sheet | Contents |
|---|---|
| 🎯 Executive Summary | KPI cards — transactions screened, alert rate, sanctions hits, SAR candidates |
| 📄 Alert Log | Filterable log of all flagged transactions by severity and type |
| 🚨 Sanctions Hits | Every match against OFAC, UN, and EU sanctions lists |
| 📈 Monthly Trends | Alert volume by typology across 12 months — with bar chart |
| 🌍 High-Risk Corridors | Top country pairs ranked by exposure |
| 📅 Regulatory Calendar | CSSF, FATF, EBA, and AMLA key deadlines through 2026 |

---

### 📁 2. FCC Programme PMO Tracker
`reports/fcc_project_status.xlsx`

A weekly PMO status tracker across six live FCC compliance programmes — exactly what a compliance PMO intern would own and maintain.

| Sheet | Contents |
|---|---|
| 🟢🟡🔴 Programme Dashboard | RAG status across all active projects at a glance |
| 📌 Project Details | Milestone-by-milestone progress with completion status |
| ✅ Action Log | Open actions, owners, due dates, and priorities |

**Projects tracked:**
- DORA ICT Incident Reporting Framework
- AMLA Readiness Programme
- FATF Travel Rule Implementation (R.16)
- Sanctions Screening Tool Upgrade
- CSSF Annual AML/CFT Questionnaire
- KYC Refresh — Tier 1 Clients

---

### 🚨 3. SAR Register
`reports/sar_register.xlsx`

A Suspicious Activity Report register aligned with Luxembourg's **goAML** filing requirements and CSSF obligations under the Law of 12 November 2004.

| Sheet | Contents |
|---|---|
| 📝 SAR Register | All SAR candidates — Filed, Under Review, or Monitoring |
| ☑️ Filing Checklist | Step-by-step goAML submission requirements |
| ⚖️ Regulatory Notes | STR obligations, tipping-off prohibition, 7-year retention rules |

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
| Large Transactions | Single transfers above €1,000,000 |
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

## ⚖️ Regulatory Framework

Every element of this project was built with reference to Clearstream's actual compliance obligations:

| Regulation | What It Requires |
|---|---|
| **CSSF Regulation 12-02** | AML/CFT framework for Luxembourg regulated entities |
| **EU AML Package** (AMLR + AMLD6) | Enhanced CDD, beneficial ownership registers, harmonised STR rules |
| **AMLA** | New EU Anti-Money Laundering Authority — direct supervision from July 2026 |
| **DORA** | ICT incident classification and reporting — in force January 2025 |
| **FATF Recommendation 16** | Travel Rule for cross-border payment data — updated June 2025 |
| **Luxembourg Law 12 Nov 2004** | STR/SAR filing obligations to CRF via goAML platform |

---

## 🛠️ Skills Demonstrated

| Skill | How |
|---|---|
| **MS Excel** | Multi-sheet workbooks with conditional formatting, pivot-ready data, RAG indicators, charts |
| **Compliance Knowledge** | AML typologies, sanctions screening, SAR filing, CSSF/FATF/AMLA regulatory framework |
| **PMO Documentation** | RAG dashboards, milestone tracking, action logs, regulatory deadline calendars |
| **Data Analysis** | 600k transactions across 3 data sources, rule-based detection, KPI aggregation |
| **Python + pandas** | Automated pipeline, report generation, 108 unit tests |

---

## 📁 Project Structure

```
clearstream-fcc-analytics/
├── 📊 reports/                     ← Excel deliverables (open these first)
├── ⚙️  src/                         ← Analytics engine
├── ⚙️  config/
│   ├── settings.yaml               ← All AML thresholds — fully configurable
│   └── pmo_projects.yaml           ← FCC programme project registry
├── 📂 data/
│   ├── raw/sanctions/              ← OFAC, UN, EU reference lists
│   └── generated/                  ← 600,000 synthetic transactions
├── 🔬 scripts/data_generation/     ← How the transaction data was built
└── ✅ tests/                        ← 108 unit tests — all passing
```

---

*Built to demonstrate end-to-end financial crime compliance analytics — from raw transaction screening through AML typology detection, sanctions matching, and management-ready Excel reporting. Designed to reflect real-world FCC workflows at a regulated post-trade financial institution.*
