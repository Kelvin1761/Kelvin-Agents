import re
from pathlib import Path

# Update au_archive_calibrator.py
path = Path("au_archive_calibrator.py")
content = path.read_text()

if "def get_true_horse_name" not in content:
    new_func = """
def get_true_horse_name(horse: dict) -> str:
    data = horse.get("_data") or {}
    facts = data.get("facts_section") or ""
    match = re.search(r"^\\[\\d+\\]\\s+([^(]+?)(?:\\s+\\(\\d+\\))?\\n", facts)
    if match:
        return match.group(1).strip()
    return str(horse.get("horse_name") or "").strip()

"""
    content = content.replace("def normalize_horse_name(name: str) -> str:", new_func + "def normalize_horse_name(name: str) -> str:")
    
    # Replace horse.get("horse_name") with get_true_horse_name(horse)
    content = content.replace('horse.get("horse_name")', 'get_true_horse_name(horse)')
    path.write_text(content)
    print("Updated au_archive_calibrator.py")


# Update re_score_archive.py
path = Path("re_score_archive.py")
content = path.read_text()
if "get_true_horse_name" not in content:
    content = content.replace("normalize_horse_name,", "normalize_horse_name,\n    get_true_horse_name,")
    content = content.replace('horse.get("horse_name")', 'get_true_horse_name(horse)')
    path.write_text(content)
    print("Updated re_score_archive.py")

