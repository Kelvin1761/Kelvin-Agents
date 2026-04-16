import sys
with open('patch_betting.py', 'r', encoding='utf-8') as f:
    code = f.read()
code = code.replace('\u2705', '[OK]')
code = code.replace('\u274c', '[FAIL]')
with open('patch_betting.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Fixed emoji in print statements")
