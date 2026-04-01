import os
d_path = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\diff.txt'
with open(d_path, 'r', encoding='utf-16le') as f:
    d = f.read()

# Fix encoding issues in the patch (like ΓöÇ which is actually a box-drawing character, probably a cp1252 to utf-8 mess up, but git apply might not care)
# If git apply fails, we'll extract manually.
out_path = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\diff_utf8.patch'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(d)
