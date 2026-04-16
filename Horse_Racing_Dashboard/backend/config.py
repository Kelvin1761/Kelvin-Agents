"""
Configuration for the Racing Dashboard backend.
"""
import os
from pathlib import Path

# Root directory of the Antigravity project
# Priority: ANTIGRAVITY_ROOT env var → Google Drive path → auto-detect fallback
_GDRIVE_PATH = Path(os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com"
    "/我的雲端硬碟/Antigravity Shared/Antigravity"
))

if os.environ.get("ANTIGRAVITY_ROOT"):
    ANTIGRAVITY_ROOT = Path(os.environ["ANTIGRAVITY_ROOT"])
elif _GDRIVE_PATH.exists():
    ANTIGRAVITY_ROOT = _GDRIVE_PATH
else:
    # Legacy fallback: parent.parent.parent of config.py
    ANTIGRAVITY_ROOT = Path(__file__).resolve().parent.parent.parent

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
