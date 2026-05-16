
import os
import sys
from pathlib import Path

# Add script path
sys.path.insert(0, r"g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\hkjc_racing\hkjc_wong_choi\scripts")
import hkjc_orchestrator as ho

def test_validation():
    intel_path = Path(r"g:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-05-13_HappyValley\_Meeting_Intelligence_Package.md")
    print(f"Testing validation for {intel_path}")
    try:
        ho.validate_intelligence_package(intel_path)
        print("✅ Validation PASSED")
    except Exception as e:
        print(f"❌ Validation FAILED: {e}")

if __name__ == "__main__":
    test_validation()
