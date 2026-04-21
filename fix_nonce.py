import json

file_path = '/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-22_HappyValley/Race_1_Logic.json'

with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

if "2" in data["horses"]:
    data["horses"]["2"]["_validation_nonce"] = "SKEL_e52bb62cd1bd428d8ee30916828e2db2"
if "3" in data["horses"]:
    data["horses"]["3"]["_validation_nonce"] = "SKEL_8d1d233aa7f3127af57f029f61b7bb52"

with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Nonces fixed.")
