import sys
from pathlib import Path

SCRIPT_DIR = Path("/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/skills/au_racing/au_race_extractor/scripts")
sys.path.append(str(SCRIPT_DIR))

from extractor import extract_all_races

# Extract just one race to a temporary dir
url = "https://www.racenet.com.au/form-guide/horse-racing/canterbury-20260527/race-1"
extract_all_races(url, Path("test_extract_output"))
