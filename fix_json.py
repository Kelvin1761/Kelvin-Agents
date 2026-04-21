import json

file_path = '/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-22_HappyValley/Race_1_Logic.json'

with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f) # This will fail if JSON is malformed

# If JSON is malformed, we can't do this easily.
