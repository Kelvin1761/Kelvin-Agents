import re
text = """🥇 [1] Maluku | 🥈 [3] Manaajem | 🥉 [6] Beverly Hills | 🏅 [10] Shoutaboutit"""

def test_parse(text):
    medals = {'🥇': 1, '🥈': 2, '🥉': 3, '🏅': 4}
    picks = []
    
    lines = text.strip().split('\n')
    for line in lines:
        if '|' in line and any(m in line for m in medals):
            # Check if multiple medals on this line
            m_count = sum(1 for m in medals if m in line)
            if m_count >= 2:
                chunks = line.split('|')
                for chunk in chunks:
                    match = re.search(r'(🥇|🥈|🥉|🏅)\s*\[?(\d+)\]?\s+([A-Za-z\s\'-]+)', chunk)
                    if match:
                        medal, num, name = match.groups()
                        # try extract grade
                        grade_m = re.search(r'\(\s*([A-DS][+\-]?)\s*\)', chunk)
                        picks.append({'rank': medals[medal], 'num': num, 'name': name.strip(), 'grade': grade_m.group(1) if grade_m else None})
                if picks:
                    return picks
    return picks

print("Result:", test_parse(text))
