"""
Import Bets — Import exported bet records JSON into the SQLite database.
Usage: python3 import_bets.py <bets_export.json>
"""
import sys
import json
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from services.bet_tracker import create_bet, update_bet_result


def import_bets(json_path: str):
    """Import bets from an exported JSON file."""
    path = Path(json_path)
    if not path.exists():
        print(f"❌ 搵唔到檔案: {json_path}")
        return

    with open(path, encoding="utf-8") as f:
        bets = json.load(f)

    if not isinstance(bets, list):
        print("❌ JSON 格式唔啱，應該係 array")
        return

    print(f"📋 準備匯入 {len(bets)} 條投注記錄...")
    imported = 0
    for b in bets:
        try:
            bet = create_bet(
                date=b["date"],
                venue=b["venue"],
                region=b.get("region", "au"),
                race_number=b["race_number"],
                horse_number=b["horse_number"],
                horse_name=b["horse_name"],
                bet_type=b.get("bet_type", "place"),
                stake=b.get("stake", 1),
                odds=b.get("odds"),
                jockey=b.get("jockey"),
                trainer=b.get("trainer"),
                consensus_type=b.get("consensus_type"),
                kelvin_grade=b.get("kelvin_grade"),
                heison_grade=b.get("heison_grade"),
            )
            bet_id = bet["id"]

            # If result is available, update it
            if b.get("result_position") is not None and b.get("status") != "pending":
                payout = b.get("payout", 0)
                update_bet_result(bet_id, b["result_position"], payout)

            imported += 1
            status = b.get("status", "pending")
            emoji = "✅" if status == "won" else ("❌" if status == "lost" else "⏳")
            print(f"  {emoji} R{b['race_number']} #{b['horse_number']} {b['horse_name']} @{b.get('odds', '—')} → {status}")

        except Exception as e:
            print(f"  ⚠️ 匯入失敗 R{b.get('race_number')} #{b.get('horse_number')}: {e}")

    print(f"\n{'=' * 40}")
    print(f"✅ 成功匯入 {imported}/{len(bets)} 條記錄到 dashboard.db")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python3 import_bets.py <bets_export.json>")
        sys.exit(1)
    import_bets(sys.argv[1])
