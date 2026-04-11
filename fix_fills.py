import sys
import re

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replacements for FILL
    content = content.replace('[FILL]', '無往績')
    content = content.replace('`[FILL]`', '`無往績`')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Fixed {filepath}")

if __name__ == "__main__":
    fix_file(sys.argv[1])
