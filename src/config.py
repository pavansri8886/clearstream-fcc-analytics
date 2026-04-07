"""
config.py
---------
Loads settings.yaml once and exposes it as CFG.
Every other file imports CFG instead of hardcoding thresholds.

Usage:
    from config import CFG
    threshold = CFG["aml_rules"]["structuring"]["threshold_eur"]
"""

from pathlib import Path
import yaml

ROOT = Path(__file__).parent.parent

with open(ROOT / "config" / "settings.yaml", encoding="utf-8") as _f:
    CFG = yaml.safe_load(_f)
