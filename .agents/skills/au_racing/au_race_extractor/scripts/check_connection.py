import os
import sys
from pathlib import Path

# Add Skill Root to sys.path
SKILL_ROOT = Path(__file__).resolve().parents[2]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from racenet_transport import fetch_nuxt_data, RacenetBlockedError

def test_connection():
    test_url = "https://www.racenet.com.au/form-guide/horse-racing/caulfield-heath-20260304/briga-fliedner-2026-lady-of-racing-finalist-race-1/overview"
    
    print("🚀 Starting Racenet Connection Probe...")
    print(f"   Target URL: {test_url}")
    print(f"   RACENET_USE_LOCAL_CHROME: {os.getenv('RACENET_USE_LOCAL_CHROME', '0')}")
    print(f"   RACENET_HEADLESS: {os.getenv('RACENET_HEADLESS', '1')}")
    
    try:
        data = fetch_nuxt_data(test_url, context_label="Probe")
        print("\n✅ SUCCESS! Connection established and __NUXT__ data retrieved.")
        print(f"   Found {len(data.get('apollo', {}).get('defaultClient', {}))} keys in Apollo Cache.")
    except RacenetBlockedError as e:
        print(f"\n❌ FAILED! Connection blocked.")
        print(f"Error details:\n{e}")
    except Exception as e:
        print(f"\n⚠️ UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    test_connection()
