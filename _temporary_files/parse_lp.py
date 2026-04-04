import json
import os

BASE_DIR = r"/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"
file_path = os.path.join(BASE_DIR, "_temporary_files", "lp_captured.json")

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

slugs = set()
for url, payload in data.items():
    # Racenet GraphQL or API returns nested data
    def find_slugs(obj):
        if isinstance(obj, dict):
            if "slug" in obj and isinstance(obj.get("slug"), str) and "race-" in obj["slug"]:
                slugs.add(obj["slug"])
            for match in obj.values():
                find_slugs(match)
        elif isinstance(obj, list):
            for item in obj:
                find_slugs(item)
    find_slugs(payload)

print("Found slugs:")
for s in sorted(slugs):
    print("  " + s)

