"""Configuration for the Racing Dashboard backend.

Code always runs from the local checkout.  Race analyses are resolved through
``wongchoi_paths`` so the dashboard reads the same data root as the HKJC and
AU pipelines (Google Drive on this machine).
"""
import os
import sys
from pathlib import Path

# ``backend/config.py`` -> ``Horse_Racing_Dashboard/backend`` -> repo root.
PROJECT_ROOT = Path(
    os.environ.get("ANTIGRAVITY_CODE_ROOT", Path(__file__).resolve().parents[2])
).expanduser()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from wongchoi_paths import AU_RACING, HK_RACING, HORSE_RACE_ANALYSIS

# Kept for code that needs project assets such as skills and ROI summaries.
ANTIGRAVITY_ROOT = PROJECT_ROOT

# The only locations scanned for race meetings and watched for report changes.
ANALYSIS_ROOT = HORSE_RACE_ANALYSIS
HKJC_ANALYSIS_ROOT = HK_RACING
AU_ANALYSIS_ROOT = AU_RACING

# Skills directories
HKJC_SKILLS = ANTIGRAVITY_ROOT / ".agents" / "skills" / "hkjc_racing"
AU_SKILLS = ANTIGRAVITY_ROOT / ".agents" / "skills" / "au_racing"

# ROI files
HKJC_ROI_PATH = HKJC_SKILLS / "HK Horse Race Summary.numbers"
AU_ROI_PATH = AU_SKILLS / "AU Horse Race Summary.numbers"

# Database
DB_PATH = Path(__file__).parent / "db" / "dashboard.db"

# Server
HOST = "0.0.0.0"
PORT = 8000
FRONTEND_ORIGINS = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"]

# Analyst names
KELVIN_FOLDER_SUFFIX = "(Kelvin)"
HEISON_FILE_PREFIX = "Heison_"

# HKJC Analysis file patterns (prefer .md, fallback .txt)
HKJC_ANALYSIS_PATTERNS = ["*_Analysis.md", "*_Analysis.txt"]
# AU Analysis file patterns  
AU_ANALYSIS_PATTERNS = ["* Analysis.md", "* Analysis.txt"]

# Rating tiers for display
RATING_TIERS = {
    "S": {"color": "#FFD700", "label": "Supreme"},
    "A+": {"color": "#22C55E", "label": "Elite"},
    "A": {"color": "#22C55E", "label": "Strong"},
    "A-": {"color": "#86EFAC", "label": "Above Avg"},
    "B+": {"color": "#3B82F6", "label": "Competitive"},
    "B": {"color": "#3B82F6", "label": "Fair"},
    "B-": {"color": "#93C5FD", "label": "Marginal"},
    "C+": {"color": "#F97316", "label": "Below Avg"},
    "C": {"color": "#F97316", "label": "Weak"},
    "C-": {"color": "#FDBA74", "label": "Poor"},
    "D+": {"color": "#F87171", "label": "Very Poor"},
    "D": {"color": "#EF4444", "label": "Eliminate"},
    "D-": {"color": "#DC2626", "label": "Hopeless"},
}
