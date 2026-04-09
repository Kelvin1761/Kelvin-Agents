import re
text = open("2026-04-08 NBA Analysis/bet365_raw_MIN_IND.txt").read()
opts = re.search(r'Points O/U\nSGM.*?\nPlayer / Last 5\n(.*?)Over\n(.*?)\nUnder\n(.*?)\nShow more', text, re.DOTALL)
print("opts found:", bool(opts))
if opts:
    print(opts.group(1)[:50])
