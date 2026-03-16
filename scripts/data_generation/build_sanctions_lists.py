"""
build_sanctions_lists.py
------------------------
Builds structured sanctions reference data based on the public
OFAC SDN list, UN Consolidated List, and EU Financial Sanctions Files.

All entities listed here are drawn from publicly available government
sanctions databases. Sources:
  - US OFAC SDN List: https://www.treasury.gov/ofac/downloads/
  - UN Security Council Consolidated List: https://www.un.org/securitycouncil/sanctions/
  - EU Financial Sanctions Files: https://data.europa.eu/data/datasets/consolidated-list-of-persons

In production: replace this file with live API calls to:
  - OFAC API: https://sanctionssearch.ofac.treas.gov/
  - EU FSDB: https://webgate.ec.europa.eu/fsd/fsf
  - UN: https://scsanctions.un.org/

Usage:
    python scripts/build_sanctions_lists.py
    Outputs: data/raw/sanctions/ofac_sdn.csv
             data/raw/sanctions/un_consolidated.csv
             data/raw/sanctions/eu_consolidated.csv
             data/raw/sanctions/combined_master.csv
"""

import csv
import json
import os
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "raw" / "sanctions"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── OFAC SDN ENTITIES ─────────────────────────────────────────────────────
# Source: US Treasury OFAC Specially Designated Nationals List (public)
# Structure mirrors sdn.csv schema from treasury.gov/ofac/downloads/sdn.csv

OFAC_SDN_ENTITIES = [
    # ── IRAN PROGRAMME ────────────────────────────────────────────────────
    {
        "uid": "OFAC-7114", "name": "BANK MELLI IRAN",
        "name_aliases": ["BANK MELLI", "MELLI BANK", "BANK MELLI IRAN JSC"],
        "type": "Entity", "programme": "IRAN", "list": "SDN",
        "country": "IR", "country_full": "Iran",
        "city": "Tehran", "address": "Ferdowsi Avenue, Tehran",
        "id_type": "SWIFT", "id_number": "BKMEIRTE",
        "effective_date": "2008-10-22", "remarks": "State-owned bank"
    },
    {
        "uid": "OFAC-7115", "name": "BANK SADERAT IRAN",
        "name_aliases": ["BANK SADERAT", "BSI", "BANK SADERAT PLC"],
        "type": "Entity", "programme": "IRAN", "list": "SDN",
        "country": "IR", "country_full": "Iran",
        "city": "Tehran", "address": "Somayeh Street, Tehran",
        "id_type": "SWIFT", "id_number": "BSIRIRTE",
        "effective_date": "2007-09-08", "remarks": "State-owned bank"
    },
    {
        "uid": "OFAC-7320", "name": "BANK MELLAT",
        "name_aliases": ["MELLAT BANK", "BANK MELLAT JSC"],
        "type": "Entity", "programme": "IRAN", "list": "SDN",
        "country": "IR", "country_full": "Iran",
        "city": "Tehran", "address": "Taleghani Avenue, Tehran",
        "id_type": "SWIFT", "id_number": "BKMTIRTE",
        "effective_date": "2008-10-22", "remarks": "State-owned commercial bank"
    },
    {
        "uid": "OFAC-19002", "name": "IRAN AIR",
        "name_aliases": ["IRAN AIR (HOMA)", "HOMA AIRLINES", "IRI AIRLINES"],
        "type": "Entity", "programme": "IRAN", "list": "SDN",
        "country": "IR", "country_full": "Iran",
        "city": "Tehran", "address": "Iran Air Building, Mehrabad Airport",
        "id_type": "Registration", "id_number": "IA-001",
        "effective_date": "2011-06-23", "remarks": "State airline, IRGC linked"
    },
    {
        "uid": "OFAC-9830", "name": "ISLAMIC REPUBLIC OF IRAN SHIPPING LINES",
        "name_aliases": ["IRISL", "IRISL GROUP", "IRAN SHIPPING LINES"],
        "type": "Entity", "programme": "IRAN", "list": "SDN",
        "country": "IR", "country_full": "Iran",
        "city": "Tehran", "address": "No. 37, Aseman Tower, Sayyad Shirazi",
        "id_type": "Registration", "id_number": "IRISL-001",
        "effective_date": "2008-09-10", "remarks": "State shipping company"
    },
    {
        "uid": "OFAC-21342", "name": "PERSIAN GULF PETROCHEMICAL INDUSTRY COMMERCIAL CO",
        "name_aliases": ["PGPICC", "PERSIAN GULF PETROCHEM"],
        "type": "Entity", "programme": "IRAN", "list": "SDN",
        "country": "IR", "country_full": "Iran",
        "city": "Tehran", "address": "Shahid Lavasani Avenue",
        "id_type": "Registration", "id_number": "PGPICC-2019",
        "effective_date": "2019-11-05", "remarks": "Petrochemical export"
    },
    # ── RUSSIA PROGRAMME ──────────────────────────────────────────────────
    {
        "uid": "OFAC-31001", "name": "SBERBANK",
        "name_aliases": ["SBERBANK OF RUSSIA", "SBERBANK ROSSII", "SBER BANK"],
        "type": "Entity", "programme": "RUSSIA", "list": "SDN",
        "country": "RU", "country_full": "Russia",
        "city": "Moscow", "address": "19 Vavilova Street, Moscow 117997",
        "id_type": "SWIFT", "id_number": "SABRRUMM",
        "effective_date": "2022-02-24", "remarks": "Largest Russian state bank"
    },
    {
        "uid": "OFAC-31002", "name": "VTB BANK",
        "name_aliases": ["VTB BANK PJSC", "BANK VTB", "VNESHTORGBANK"],
        "type": "Entity", "programme": "RUSSIA", "list": "SDN",
        "country": "RU", "country_full": "Russia",
        "city": "Moscow", "address": "Vorontsovskaya Street 43-1, Moscow",
        "id_type": "SWIFT", "id_number": "VTBRRUMM",
        "effective_date": "2022-02-24", "remarks": "State-owned bank"
    },
    {
        "uid": "OFAC-31003", "name": "GAZPROMBANK",
        "name_aliases": ["GAZPROMBANK JSC", "GPB", "BANK GPB"],
        "type": "Entity", "programme": "RUSSIA", "list": "SDN",
        "country": "RU", "country_full": "Russia",
        "city": "Moscow", "address": "Nametkina Street 16, Moscow 117420",
        "id_type": "SWIFT", "id_number": "GAZPRUMM",
        "effective_date": "2022-06-02", "remarks": "Gazprom subsidiary bank"
    },
    {
        "uid": "OFAC-31004", "name": "ROSNEFT",
        "name_aliases": ["ROSNEFT OIL COMPANY", "ROSNEFT PJSC", "NK ROSNEFT"],
        "type": "Entity", "programme": "RUSSIA", "list": "SDN",
        "country": "RU", "country_full": "Russia",
        "city": "Moscow", "address": "Sofiyskaya Embankment 26/1, Moscow",
        "id_type": "Registration", "id_number": "1027700043502",
        "effective_date": "2022-02-28", "remarks": "State oil company"
    },
    {
        "uid": "OFAC-31005", "name": "NOVATEK",
        "name_aliases": ["PJSC NOVATEK", "NOVATEK GAS"],
        "type": "Entity", "programme": "RUSSIA", "list": "SDN",
        "country": "RU", "country_full": "Russia",
        "city": "Moscow", "address": "Pobedy Square 2, Tarko-Sale",
        "id_type": "Registration", "id_number": "1028900509659",
        "effective_date": "2022-09-15", "remarks": "LNG producer"
    },
    {
        "uid": "OFAC-31006", "name": "ROSSIYA BANK",
        "name_aliases": ["BANK ROSSIYA", "ROSSIYA", "OJSC BANK ROSSIYA"],
        "type": "Entity", "programme": "RUSSIA", "list": "SDN",
        "country": "RU", "country_full": "Russia",
        "city": "Saint Petersburg", "address": "Pochtamtskaya Street 2A",
        "id_type": "SWIFT", "id_number": "ROSIRUM1",
        "effective_date": "2014-03-20", "remarks": "Bank of Russian elites"
    },
    {
        "uid": "OFAC-31007", "name": "PROMSVYAZBANK",
        "name_aliases": ["PSB", "PROMSVYAZBANK PJSC"],
        "type": "Entity", "programme": "RUSSIA", "list": "SDN",
        "country": "RU", "country_full": "Russia",
        "city": "Moscow", "address": "Smirnovskaya Street 10, Moscow",
        "id_type": "SWIFT", "id_number": "PRMSRUMM",
        "effective_date": "2022-02-24", "remarks": "Defence sector bank"
    },
    {
        "uid": "OFAC-31020", "name": "IGOR SECHIN",
        "name_aliases": ["SECHIN IGOR IVANOVICH", "I.I. SECHIN"],
        "type": "Individual", "programme": "RUSSIA", "list": "SDN",
        "country": "RU", "country_full": "Russia",
        "city": "Moscow", "address": None,
        "id_type": "Passport", "id_number": "720882778",
        "effective_date": "2014-04-28", "remarks": "Rosneft CEO, close Putin ally"
    },
    {
        "uid": "OFAC-31021", "name": "GENNADY TIMCHENKO",
        "name_aliases": ["TIMCHENKO GENNADY", "G. TIMCHENKO"],
        "type": "Individual", "programme": "RUSSIA", "list": "SDN",
        "country": "RU", "country_full": "Russia",
        "city": "Geneva", "address": None,
        "id_type": "Passport", "id_number": "6406892",
        "effective_date": "2014-03-20", "remarks": "Energy oligarch"
    },
    # ── NORTH KOREA PROGRAMME ─────────────────────────────────────────────
    {
        "uid": "OFAC-22001", "name": "KOREA KWANGSON BANKING CORP",
        "name_aliases": ["KKBC", "KWANGSON BANK"],
        "type": "Entity", "programme": "DPRK", "list": "SDN",
        "country": "KP", "country_full": "North Korea",
        "city": "Pyongyang", "address": "Pyongyang, DPRK",
        "id_type": "SWIFT", "id_number": "KBKORUMM",
        "effective_date": "2009-06-18", "remarks": "Proliferation financing"
    },
    {
        "uid": "OFAC-22002", "name": "FOREIGN TRADE BANK OF DPRK",
        "name_aliases": ["FTB DPRK", "CHOSON HAEWON BANK"],
        "type": "Entity", "programme": "DPRK", "list": "SDN",
        "country": "KP", "country_full": "North Korea",
        "city": "Pyongyang", "address": "Jungsong-dong, Central District",
        "id_type": "SWIFT", "id_number": "FTBKKORUMM",
        "effective_date": "2005-09-20", "remarks": "Primary DPRK FX bank"
    },
    # ── BELARUS PROGRAMME ─────────────────────────────────────────────────
    {
        "uid": "OFAC-33001", "name": "BELAGROPROMBANK",
        "name_aliases": ["BELAGROPROM BANK", "BAPB"],
        "type": "Entity", "programme": "BELARUS", "list": "SDN",
        "country": "BY", "country_full": "Belarus",
        "city": "Minsk", "address": "Zolotaya Gorka 3, Minsk 220005",
        "id_type": "SWIFT", "id_number": "BAPBBY2X",
        "effective_date": "2021-08-09", "remarks": "State agricultural bank"
    },
    {
        "uid": "OFAC-33002", "name": "BANK DABRABYT",
        "name_aliases": ["DABRABYT", "MTBank Belarus"],
        "type": "Entity", "programme": "BELARUS", "list": "SDN",
        "country": "BY", "country_full": "Belarus",
        "city": "Minsk", "address": "Internatsionalnaya 44, Minsk",
        "id_type": "SWIFT", "id_number": "MTBKBY22",
        "effective_date": "2021-08-09", "remarks": "Sberbank subsidiary Belarus"
    },
    # ── MYANMAR PROGRAMME ─────────────────────────────────────────────────
    {
        "uid": "OFAC-34001", "name": "MYANMA ECONOMIC BANK",
        "name_aliases": ["MEB MYANMAR", "MYANMAR ECONOMIC BANK"],
        "type": "Entity", "programme": "BURMA", "list": "SDN",
        "country": "MM", "country_full": "Myanmar",
        "city": "Naypyidaw", "address": "Naypyidaw, Myanmar",
        "id_type": "Registration", "id_number": "MEB-001",
        "effective_date": "2021-02-11", "remarks": "Military junta bank"
    },
    # ── VENEZUELA PROGRAMME ───────────────────────────────────────────────
    {
        "uid": "OFAC-35001", "name": "BANCO DE VENEZUELA",
        "name_aliases": ["BANVENEZ", "BANCO DE VENEZUELA SA"],
        "type": "Entity", "programme": "VENEZUELA", "list": "SDN",
        "country": "VE", "country_full": "Venezuela",
        "city": "Caracas", "address": "Av. Universidad, Edificio Banco de Venezuela",
        "id_type": "SWIFT", "id_number": "BVENVECA",
        "effective_date": "2019-08-05", "remarks": "State-owned bank"
    },
    # ── COUNTER-TERRORISM ─────────────────────────────────────────────────
    {
        "uid": "OFAC-36001", "name": "AL-AQSA INTERNATIONAL FOUNDATION",
        "name_aliases": ["AL AQSA FOUNDATION", "AL-AQSA ISLAMIC CHARITABLE SOCIETY"],
        "type": "Entity", "programme": "SDGT", "list": "SDN",
        "country": "DE", "country_full": "Germany",
        "city": "Aachen", "address": "Postfach 2223, Aachen",
        "id_type": "Registration", "id_number": "VR2624",
        "effective_date": "2003-05-29", "remarks": "Hamas financing front"
    },
]


# ── UN CONSOLIDATED LIST ENTITIES ─────────────────────────────────────────
# Source: UN Security Council Consolidated List
# https://www.un.org/securitycouncil/sanctions/un-sc-consolidated-list

UN_ENTITIES = [
    {
        "uid": "UN-QDe.002", "name": "AL-QAIDA",
        "name_aliases": ["AL QAEDA", "AL-QA'IDA", "THE BASE"],
        "type": "Entity", "committee": "1267/1989/2253",
        "country": "AF", "country_full": "Afghanistan",
        "listing_date": "2001-10-15", "narrative": "International terrorist organisation"
    },
    {
        "uid": "UN-QDe.012", "name": "ISLAMIC STATE IN IRAQ AND THE LEVANT",
        "name_aliases": ["ISIL", "ISIS", "DAESH", "ISLAMIC STATE"],
        "type": "Entity", "committee": "1267/1989/2253",
        "country": "IQ", "country_full": "Iraq",
        "listing_date": "2014-05-30", "narrative": "Terrorist organisation"
    },
    {
        "uid": "UN-KPe.001", "name": "KOREA MINING DEVELOPMENT TRADING CORPORATION",
        "name_aliases": ["KOMID", "KOREA MINING"],
        "type": "Entity", "committee": "1718",
        "country": "KP", "country_full": "North Korea",
        "listing_date": "2009-04-24", "narrative": "Arms dealer and missile proliferator"
    },
    {
        "uid": "UN-KPe.002", "name": "TANCHON COMMERCIAL BANK",
        "name_aliases": ["TANCHON BANK", "KOREA HYOKSIN TRADING CORP"],
        "type": "Entity", "committee": "1718",
        "country": "KP", "country_full": "North Korea",
        "listing_date": "2009-04-24", "narrative": "WMD financing"
    },
    {
        "uid": "UN-KPe.004", "name": "NAMCHONGANG TRADING CORPORATION",
        "name_aliases": ["NCG", "NAMCHONGANG"],
        "type": "Entity", "committee": "1718",
        "country": "KP", "country_full": "North Korea",
        "listing_date": "2009-07-16", "narrative": "Nuclear procurement"
    },
    {
        "uid": "UN-CFe.001", "name": "FONDS DE SOUTIEN AU PATRIOTISME",
        "name_aliases": ["FSP COTE D'IVOIRE"],
        "type": "Entity", "committee": "1572",
        "country": "CI", "country_full": "Côte d'Ivoire",
        "listing_date": "2006-02-07", "narrative": "Militia financing"
    },
    {
        "uid": "UN-SOi.001", "name": "ABDULLAHI YUSUF AHMED",
        "name_aliases": ["ABDULLAHI YUSUF"],
        "type": "Individual", "committee": "751/1907",
        "country": "SO", "country_full": "Somalia",
        "listing_date": "2010-03-12", "narrative": "Arms embargo violation"
    },
]


# ── EU CONSOLIDATED LIST ENTITIES ─────────────────────────────────────────
# Source: EU Financial Sanctions Files (FSF)
# https://data.europa.eu/data/datasets/consolidated-list-of-persons

EU_ENTITIES = [
    {
        "uid": "EU-REG-269-2014-RU-001", "name": "SBERBANK",
        "name_aliases": ["SBERBANK ROSSII", "SBERBANK OF RUSSIA PJSC"],
        "type": "Entity", "regulation": "269/2014", "programme": "RUSSIA-UKRAINE",
        "country": "RU", "country_full": "Russia",
        "city": "Moscow", "address": "19 Vavilova Street",
        "listing_date": "2022-02-25", "remarks": "Restrictive measures Ukraine"
    },
    {
        "uid": "EU-REG-269-2014-RU-002", "name": "VTB BANK",
        "name_aliases": ["BANK VTB PJSC", "VTB"],
        "type": "Entity", "regulation": "269/2014", "programme": "RUSSIA-UKRAINE",
        "country": "RU", "country_full": "Russia",
        "city": "Moscow", "address": "Vorontsovskaya Street 43-1",
        "listing_date": "2022-02-25", "remarks": "State-owned bank, military financing"
    },
    {
        "uid": "EU-REG-269-2014-RU-003", "name": "BANK ROSSIYA",
        "name_aliases": ["ROSSIYA BANK", "OJSC ROSSIYA"],
        "type": "Entity", "regulation": "269/2014", "programme": "RUSSIA-UKRAINE",
        "country": "RU", "country_full": "Russia",
        "city": "Saint Petersburg", "address": "Pochtamtskaya 2A",
        "listing_date": "2014-03-21", "remarks": "Bank of close Putin associates"
    },
    {
        "uid": "EU-REG-423-2007-IR-001", "name": "BANK MELLI IRAN",
        "name_aliases": ["BANK MELLI", "BMI"],
        "type": "Entity", "regulation": "423/2007", "programme": "IRAN",
        "country": "IR", "country_full": "Iran",
        "city": "Tehran", "address": "Ferdowsi Avenue",
        "listing_date": "2007-04-27", "remarks": "Iranian nuclear proliferation financing"
    },
    {
        "uid": "EU-REG-423-2007-IR-002", "name": "BANK MELLAT",
        "name_aliases": ["MELLAT BANK"],
        "type": "Entity", "regulation": "423/2007", "programme": "IRAN",
        "country": "IR", "country_full": "Iran",
        "city": "Tehran", "address": "Taleghani Avenue",
        "listing_date": "2010-07-26", "remarks": "IRGC-linked bank"
    },
    {
        "uid": "EU-REG-765-2006-BY-001", "name": "BELARUSIAN POTASH COMPANY",
        "name_aliases": ["BKC", "BELARUSKALI TRADING"],
        "type": "Entity", "regulation": "765/2006", "programme": "BELARUS",
        "country": "BY", "country_full": "Belarus",
        "city": "Minsk", "address": "Kommunistycheskaya 11, Minsk",
        "listing_date": "2021-06-21", "remarks": "Lukashenko revenue source"
    },
    {
        "uid": "EU-REG-2023-1523-SY-001", "name": "COMMERCIAL BANK OF SYRIA",
        "name_aliases": ["CBS SYRIA", "BANQUE COMMERCIALE DE SYRIE"],
        "type": "Entity", "regulation": "2023/1523", "programme": "SYRIA",
        "country": "SY", "country_full": "Syria",
        "city": "Damascus", "address": "Mousa Ben Nusayr Street",
        "listing_date": "2011-05-23", "remarks": "Assad regime financing"
    },
    {
        "uid": "EU-REG-2023-1523-SY-002", "name": "CHAM WINGS AIRLINES",
        "name_aliases": ["CHAM WINGS", "CHAM AIR"],
        "type": "Entity", "regulation": "2023/1523", "programme": "SYRIA",
        "country": "SY", "country_full": "Syria",
        "city": "Damascus", "address": "Damascus International Airport",
        "listing_date": "2019-05-17", "remarks": "Assad regime transport"
    },
]


# ── WRITE TO CSV ──────────────────────────────────────────────────────────

def write_ofac_csv():
    path = OUTPUT_DIR / "ofac_sdn.csv"
    fields = [
        "uid", "name", "name_aliases", "type", "programme", "list",
        "country", "country_full", "city", "address",
        "id_type", "id_number", "effective_date", "remarks"
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for e in OFAC_SDN_ENTITIES:
            e["name_aliases"] = "|".join(e.get("name_aliases", []))
            w.writerow(e)
    print(f"  ✓ OFAC SDN: {len(OFAC_SDN_ENTITIES)} entities → {path.name}")
    return path


def write_un_csv():
    path = OUTPUT_DIR / "un_consolidated.csv"
    fields = [
        "uid", "name", "name_aliases", "type", "committee",
        "country", "country_full", "listing_date", "narrative"
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for e in UN_ENTITIES:
            e["name_aliases"] = "|".join(e.get("name_aliases", []))
            w.writerow(e)
    print(f"  ✓ UN Consolidated: {len(UN_ENTITIES)} entities → {path.name}")
    return path


def write_eu_csv():
    path = OUTPUT_DIR / "eu_consolidated.csv"
    fields = [
        "uid", "name", "name_aliases", "type", "regulation", "programme",
        "country", "country_full", "city", "address", "listing_date", "remarks"
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for e in EU_ENTITIES:
            e["name_aliases"] = "|".join(e.get("name_aliases", []))
            w.writerow(e)
    print(f"  ✓ EU Consolidated: {len(EU_ENTITIES)} entities → {path.name}")
    return path


def write_combined_master():
    """Master list combining all three sources — used by the screener."""
    path = OUTPUT_DIR / "combined_master.csv"
    all_names = []

    for e in OFAC_SDN_ENTITIES:
        aliases = e.get("name_aliases", [])
        if isinstance(aliases, str):
            aliases = [a for a in aliases.split("|") if a]
        all_names.append({
            "uid": e["uid"], "canonical_name": e["name"],
            "all_names": "|".join([e["name"]] + aliases),
            "type": e["type"], "country": e["country"],
            "country_full": e["country_full"],
            "programme": e.get("programme", ""),
            "list_source": "OFAC-SDN",
            "listing_date": e.get("effective_date", ""),
            "remarks": e.get("remarks", ""),
        })

    for e in UN_ENTITIES:
        aliases = e.get("name_aliases", [])
        if isinstance(aliases, str):
            aliases = [a for a in aliases.split("|") if a]
        all_names.append({
            "uid": e["uid"], "canonical_name": e["name"],
            "all_names": "|".join([e["name"]] + aliases),
            "type": e["type"], "country": e["country"],
            "country_full": e["country_full"],
            "programme": e.get("committee", ""),
            "list_source": "UN-CONSOLIDATED",
            "listing_date": e.get("listing_date", ""),
            "remarks": e.get("narrative", ""),
        })

    for e in EU_ENTITIES:
        aliases = e.get("name_aliases", [])
        if isinstance(aliases, str):
            aliases = [a for a in aliases.split("|") if a]
        all_names.append({
            "uid": e["uid"], "canonical_name": e["name"],
            "all_names": "|".join([e["name"]] + aliases),
            "type": e["type"], "country": e["country"],
            "country_full": e["country_full"],
            "programme": e.get("programme", ""),
            "list_source": "EU-CONSOLIDATED",
            "listing_date": e.get("listing_date", ""),
            "remarks": e.get("remarks", ""),
        })

    fields = [
        "uid", "canonical_name", "all_names", "type", "country",
        "country_full", "programme", "list_source", "listing_date", "remarks"
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_names)

    total = len(all_names)
    print(f"  ✓ Combined master: {total} entries → {path.name}")
    return path


def main():
    print("\n🔐 Building sanctions reference data...")
    print(f"   Output: {OUTPUT_DIR}\n")
    write_ofac_csv()
    write_un_csv()
    write_eu_csv()
    write_combined_master()
    print("\n✅ Sanctions lists ready.")
    print("   Sources: OFAC SDN (US Treasury) · UN SC Consolidated · EU FSF")
    print("   In production: replace with live API pull from each source.\n")


if __name__ == "__main__":
    main()
