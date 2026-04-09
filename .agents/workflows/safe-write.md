---
description: How to safely write files without IDE hangs on macOS. MUST READ before any file writing.
---

# Safe File Writing Protocol (Anti-Stuck)

## ⛔ BANNED TOOLS — WILL CAUSE IDE HANG
The following tools are **COMPLETELY BANNED** for ANY file, ANY path, ANY size:
- `write_to_file` — ❌ BANNED (even for /tmp!)
- `replace_file_content` — ❌ BANNED
- `multi_replace_file_content` — ❌ BANNED

These tools route through the IDE's JSON pipe which hangs on macOS.

## ✅ ONLY ALLOWED METHOD: `run_command`

### Pattern A: Write a small script to /tmp (< 50 lines)
```bash
// turbo
cat > /tmp/my_script.py << 'EOF'
import json
print("hello")
EOF
echo "OK: $(wc -l < /tmp/my_script.py) lines"
```

### Pattern B: Write analysis content to target file
```bash
cat > /tmp/batch_N.md << 'ENDOFCONTENT'
[your content here]
ENDOFCONTENT
echo "HEREDOC_OK: $(wc -l < /tmp/batch_N.md) lines"
```
Then copy to target:
```bash
# Overwrite:
cp /tmp/batch_N.md "${TARGET_DIR}/${FILENAME}"
# Append:
cat /tmp/batch_N.md >> "${TARGET_DIR}/${FILENAME}"
```

### Pattern C: Verify after writing
```bash
// turbo
tail -3 "${TARGET_DIR}/${FILENAME}"
echo "---"
wc -l "${TARGET_DIR}/${FILENAME}"
```

## 🧠 Self-Check Trigger
Before ANY file creation/edit, ask yourself:
> "Am I about to use write_to_file, replace_file_content, or multi_replace_file_content?"
> If YES → ⛔ STOP → Use `run_command` + heredoc instead.

## ⚠️ Common Mistake
Even `/tmp` files MUST use `run_command` heredoc. The IDE hang affects ALL paths.
