#!/bin/bash
# architect_ralph_loop.sh
# (Phase 1.2: Agent Architect Ralph Loop)
# This script operates as a Background Pre-commit Hook for the Agent Architect.
# It parses any newly generated SKILL.md rules to ensure the Gemini Anti-Laziness protocols
# and <think> loops are firmly established. If not, it rejects the file write.

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 /path/to/SKILL.md"
    exit 1
fi

TARGET_FILE="$1"
SCORE=100

echo "🛡️ Architect Ralph Loop Initializing..."
echo "📄 Scanning file: $TARGET_FILE"

if [ ! -f "$TARGET_FILE" ]; then
    echo "❌ Error: File not found."
    exit 1
fi

# Check 1: Extended Thinking (<thinking> Block Directive)
if ! grep -Eqi "(<thinking>|<think>|Extended Thinking)" "$TARGET_FILE" ; then
    echo "  ⚠️ Validation Failed (-30): Missing <thinking> loop or Extended Thinking directive."
    SCORE=$((SCORE - 30))
else
    echo "  ✅ Extended Thinking loop detected."
fi

# Check 2: Emoji / Anti-Laziness protocols
if ! grep -Eqi "(Anti-laziness|CRITICAL|MUST|Emoji)" "$TARGET_FILE" ; then
    echo "  ⚠️ Validation Failed (-20): Missing rigorous Anti-laziness protocol reinforcement."
    SCORE=$((SCORE - 20))
else
    echo "  ✅ Anti-Laziness reinforcement detected."
fi

# Check 3: MCP Memory Persistence
if ! grep -Eqi "Memory|MCP" "$TARGET_FILE" ; then
    echo "  ⚠️ Validation Failed (-10): Missing MCP Memory persistence configuration."
    SCORE=$((SCORE - 10))
else
    echo "  ✅ MCP Memory Persistence detected."
fi

echo "============================================="
echo "📊 Architect Confidence Score: $SCORE / 100"

if [ "$SCORE" -lt 80 ]; then
    echo "❌ RALPH LOOP REJECTION: The generated SKILL.md configuration is too shallow."
    echo "   Action: The Agent Architect MUST rewrite the agent prompt integrating the missing robust paradigms."
    exit 1
else
    echo "🟢 RALPH LOOP APPROVAL: The agent prompt looks highly resilient. Proceed to commit."
    exit 0
fi
