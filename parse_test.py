import re

text = open("2026-04-10 Cranbourne Race 1-8/04-10 Race 4 Formguide.md").read()
horse_num = 9
pattern = re.compile(rf'^\[{horse_num}\]\s+', re.MULTILINE)
match = pattern.search(text)
if match:
    next_horse = re.search(r'^\[\d+\]\s+', text[match.end():], re.MULTILINE)
    section_end = match.end() + next_horse.start() if next_horse else len(text)
    section = text[match.start():section_end]
    print(f"Matched {len(section)} characters for horse {horse_num}")
    
    race_simple = re.compile(
        r'^(\S.+?)\s+R(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+m)\s+cond:(\S+)\s+\$([0-9,]+)',
        re.MULTILINE
    )
    matches = list(race_simple.finditer(section))
    print(f"Found {len(matches)} races")
else:
    print("Horse not found!")
