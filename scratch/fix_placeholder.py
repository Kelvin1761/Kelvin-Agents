import glob
import os

files = glob.glob('04-15_HappyValley Race *Analysis.md')
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Replace the exact PLACEHOLDER block
    to_replace = "```csv\nPLACEHOLDER\n```"
    if to_replace in content:
        content = content.replace(to_replace, "<!-- MONTE_CARLO_PYTHON_INJECT_HERE -->")
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f"Replaced PLACEHOLDER in {f}")
    else:
        print(f"PLACEHOLDER not found in {f}")
