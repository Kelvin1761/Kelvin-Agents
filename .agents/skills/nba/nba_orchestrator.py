#!/usr/bin/env python3
"""
nba_orchestrator.py — NBA Wong Choi Pipeline Orchestrator V3
=============================================================
Unified orchestrator merging Skills V2 pipeline + Scripts V9 features + AU NEXT_CMD pattern.

Pipeline:
  Phase 0:  claw_sportsbet_odds.py  → Sportsbet Odds JSON
  Phase 1A: nba_extractor.py        → nba_game_data_{TAG}.json (L10 from nba_api)
  Phase 1B: generate_nba_reports.py → Game_{TAG}_Full_Analysis.md (pre-filled skeleton)
  Phase 2:  LLM Analyst fills [FILL] fields (if any)
  Phase 3:  generate_nba_sgm_reports.py → Master SGM + Banker reports

Usage:
  python nba_orchestrator.py --date 2026-04-16
  python nba_orchestrator.py --date 2026-04-16 --game ATL_NYK
  python nba_orchestrator.py --date 2026-04-16 --list
  python nba_orchestrator.py --date 2026-04-16 --status
  python nba_orchestrator.py --date 2026-04-16 --compile-only
  python nba_orchestrator.py --date 2026-04-16 --auto

Version: 3.0.0
"""
from __future__ import annotations
import argparse
import datetime
import glob
import json
import os
import shutil
import subprocess
import sys

# ─── Cross-Platform Python ──────────────────────────────────────────────
PYTHON = "python3" if shutil.which("python3") else "python"

# ─── Path Constants ─────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
SKILLS_DIR = SCRIPT_DIR  # .agents/skills/nba/

CLAW_SPORTSBET = os.path.join(SKILLS_DIR, "nba_data_extractor", "scripts", "claw_sportsbet_odds.py")
NBA_EXTRACTOR = os.path.join(SKILLS_DIR, "nba_data_extractor", "scripts", "nba_extractor.py")
GENERATE_REPORTS = os.path.join(SKILLS_DIR, "nba_wong_choi", "scripts", "generate_nba_reports.py")
VALIDATE_OUTPUT = os.path.join(SKILLS_DIR, "nba_wong_choi", "scripts", "validate_nba_output.py")
GENERATE_SGM = os.path.join(SKILLS_DIR, "nba_wong_choi", "scripts", "generate_nba_sgm_reports.py")


# ─── Preflight ──────────────────────────────────────────────────────────

def preflight_check() -> bool:
    """Verify critical scripts exist before starting pipeline."""
    ok = True
    for label, path in [
        ("NBA Extractor", NBA_EXTRACTOR),
        ("Report Generator", GENERATE_REPORTS),
        ("Sportsbet Claw", CLAW_SPORTSBET),
        ("SGM Report Generator", GENERATE_SGM),
    ]:
        if not os.path.exists(path):
            print(f"❌ [Preflight] {label} 找不到: {path}")
            ok = False
    if not ok:
        print("⛔ Preflight 失敗 — 請確認 skill 目錄結構完整。")
    return ok


# ─── Utilities ──────────────────────────────────────────────────────────

def get_target_dir(date_str: str) -> str:
    target_dir = os.path.join(WORKSPACE_ROOT, f"{date_str} NBA Analysis")
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


def run_script(script_path: str, args_list: list, label: str = "Script") -> bool:
    if not os.path.exists(script_path):
        print(f"❌ [{label}] 找不到腳本: {script_path}")
        return False
    cmd = [PYTHON, script_path] + args_list
    print(f"🔧 [{label}] 執行: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            # Show last 500 chars to avoid flooding terminal
            output = result.stdout.strip()
            if len(output) > 500:
                print(f"   ...{output[-500:]}")
            else:
                print(f"   {output}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️ [{label}] 執行失敗 (exit code: {e.returncode})")
        if e.stderr:
            print(f"   stderr: {e.stderr[:300]}")
        return False


def discover_sportsbet_jsons(target_dir: str) -> list:
    pattern = os.path.join(target_dir, "Sportsbet_Odds_*.json")
    return sorted(f for f in glob.glob(pattern)
                  if "TEST" not in f and "MIN" not in f and "GEMINI" not in f)


def extract_game_tag(json_path: str) -> str:
    filename = os.path.basename(json_path)
    return filename.replace("Sportsbet_Odds_", "").replace(".json", "")


def check_skeleton_exists(target_dir: str, game_tag: str) -> str | None:
    patterns = [
        f"Game_{game_tag}_Full_Analysis.md",
        f"Game_*_{game_tag}_Full_Analysis.md",
    ]
    for pat in patterns:
        matches = glob.glob(os.path.join(target_dir, pat))
        for m in matches:
            if os.path.getsize(m) >= 5000:
                return m
    return None


# ─── State Persistence ──────────────────────────────────────────────────

def write_state(target_dir: str, game_tags: list, phase: str):
    state_file = os.path.join(target_dir, "_nba_session_state.md")
    now = datetime.datetime.now().isoformat()
    with open(state_file, "a", encoding="utf-8") as fh:
        fh.write(f"\n🔒 NBA_ORCHESTRATOR: {phase.upper()} | {now}\n")
        fh.write(f"   Games: {', '.join(game_tags)}\n")


# ─── NEXT_CMD Auto-Loop (AU Pattern) ────────────────────────────────────

def _next_cmd(date_str: str, extra_args: str = ""):
    """Print machine-readable re-run command for LLM auto-execution."""
    rel_path = os.path.relpath(os.path.abspath(__file__), WORKSPACE_ROOT)
    cmd = f"{PYTHON} {rel_path} --date {date_str} --auto"
    if extra_args:
        cmd += f" {extra_args}"
    print(f"\nNEXT_CMD: {cmd}")


def _count_fill_residuals(target_dir: str) -> int:
    """Count remaining [FILL] placeholders across all analysis files."""
    count = 0
    for md in glob.glob(os.path.join(target_dir, "Game_*_Full_Analysis.md")):
        with open(md, "r", encoding="utf-8") as f:
            count += f.read().count("[FILL]")
    return count


# ─── Per-Game Pipeline ──────────────────────────────────────────────────

def process_single_game(game_tag: str, sportsbet_json: str, target_dir: str,
                        date_str: str, game_num: int | None = None,
                        skip_extractor: bool = False) -> bool:
    prefix = f"Game {game_num}" if game_num else game_tag
    print(f"\n{'='*60}")
    print(f"🏀 [{prefix}] {game_tag} — 開始 Pipeline")
    print(f"{'='*60}")

    # ── Check if already completed ──
    existing = check_skeleton_exists(target_dir, game_tag)
    if existing:
        print(f"✅ [{prefix}] 已存在合格報告: {os.path.basename(existing)} ({os.path.getsize(existing)} bytes)")
        print(f"   跳過。如需重做，請刪除該文件後重跑。")
        return True

    # ── Phase 1A: nba_extractor.py (球員深度數據) ──
    ext_date = date_str.replace("-", "")
    extractor_json = os.path.join(target_dir, f"nba_game_data_{game_tag}.json")

    if os.path.exists(extractor_json):
        print(f"✅ [{prefix}] Extractor JSON 已存在: {os.path.basename(extractor_json)}")
    elif skip_extractor:
        print(f"⚠️ [{prefix}] --skip-extractor: 建立 fallback JSON...")
        _create_minimal_extractor_json(sportsbet_json, extractor_json, game_tag)
    else:
        print(f"\n📡 [{prefix}] Phase 1A: 執行 nba_extractor.py 提取球員數據...")
        extractor_ok = run_script(NBA_EXTRACTOR, [
            "--date", ext_date,
            "--game", game_tag,
            "--output", extractor_json
        ], label=f"{prefix} Extractor")

        if not extractor_ok or not os.path.exists(extractor_json):
            print(f"❌ [{prefix}] nba_extractor.py 失敗！無 L10 數據。")
            print(f"   可能原因: nba_api 未安裝 / API 限流 / ESPN 日期轉換問題")
            print(f"   ⛔ 跳過此賽事 — 冇真實 L10 gamelog 不進行分析。")
            return False

    # ── Phase 1B: generate_nba_reports.py (Full Analysis) ──
    analysis_md = os.path.join(target_dir, f"Game_{game_tag}_Full_Analysis.md")
    print(f"\n📊 [{prefix}] Phase 1B: 執行 generate_nba_reports.py 生成分析報告...")
    report_ok = run_script(GENERATE_REPORTS, [
        "--sportsbet", sportsbet_json,
        "--extractor", extractor_json,
        "--output", analysis_md
    ], label=f"{prefix} Report Generator")

    if not report_ok or not os.path.exists(analysis_md):
        print(f"❌ [{prefix}] 分析報告生成失敗！")
        return False

    analysis_size = os.path.getsize(analysis_md)
    print(f"✅ [{prefix}] 分析報告已生成: {os.path.basename(analysis_md)} ({analysis_size} bytes)")

    if analysis_size < 2000:
        print(f"⚠️ [{prefix}] 報告大小偏小 ({analysis_size} bytes)，可能數據不足。")

    # ── Validation (防火牆) ──
    if os.path.exists(VALIDATE_OUTPUT):
        print(f"\n🛡️ [{prefix}] Validation: 執行 validate_nba_output.py...")
        validate_ok = run_script(VALIDATE_OUTPUT, [analysis_md], label=f"{prefix} Validator")
        if not validate_ok:
            print(f"⚠️ [{prefix}] 防火牆檢查未通過。請人工檢查報告。")

    print(f"\n🎉 [{prefix}] {game_tag} Pipeline 完成！")
    return True


def _create_minimal_extractor_json(sportsbet_json: str, output_path: str, game_tag: str) -> bool:
    try:
        with open(sportsbet_json, 'r', encoding='utf-8') as f:
            sb = json.load(f)
        parts = game_tag.split("_")
        away_abbr = parts[0] if len(parts) >= 2 else "?"
        home_abbr = parts[1] if len(parts) >= 2 else "?"
        unique_players = set()
        for cat, players in sb.get("player_props", {}).items():
            for p_name in players.keys():
                unique_players.add(p_name)
        minimal = {
            "meta": {"date": sb.get("extraction_time", ""),
                     "away": {"name": away_abbr, "abbr": away_abbr},
                     "home": {"name": home_abbr, "abbr": home_abbr}},
            "odds": sb.get("game_lines", {}),
            "injuries": {}, "news": {}, "team_stats": {},
            "players": {away_abbr: [{"name": p} for p in unique_players], home_abbr: []},
            "key_defenders": {}, "usage_redistribution": {},
            "correlation_warnings": {},
            "_fallback_mode": True,
            "_note": "Fallback JSON — Sportsbet data only, no L10 gamelog."
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(minimal, f, ensure_ascii=False, indent=2)
        print(f"✅ Fallback extractor JSON: {os.path.basename(output_path)}")
        return True
    except Exception as e:
        print(f"❌ Fallback JSON 建立失敗: {e}")
        return False


# ─── Status Report ──────────────────────────────────────────────────────

def print_status(target_dir: str, game_tags: list):
    print(f"\n📋 Pipeline 狀態 ({os.path.basename(target_dir)})")
    print(f"{'─'*50}")
    for tag in game_tags:
        sb = "✅" if os.path.exists(os.path.join(target_dir, f"Sportsbet_Odds_{tag}.json")) else "❌"
        ext = "✅" if os.path.exists(os.path.join(target_dir, f"nba_game_data_{tag}.json")) else "❌"
        skel = "✅" if os.path.exists(os.path.join(target_dir, f"Game_{tag}_Full_Analysis.md")) else "❌"
        print(f"  {tag}: Odds {sb} | Extractor {ext} | Analysis {skel}")
    sgm = "✅" if os.path.exists(os.path.join(target_dir, "NBA_All_SGM_Report.txt")) else "❌"
    bnk = "✅" if os.path.exists(os.path.join(target_dir, "NBA_Banker_Report.txt")) else "❌"
    print(f"\n  匯總: SGM {sgm} | Banker {bnk}")


# ─── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="NBA Wong Choi Pipeline Orchestrator V3 — "
                    "Sportsbet Claw → Extractor → Report → Validator → SGM"
    )
    parser.add_argument("--date", help="分析日期 (YYYY-MM-DD)。預設為今日。")
    parser.add_argument("--game", help="只分析指定賽事 (e.g., ATL_NYK)。")
    parser.add_argument("--list", action="store_true", help="列出可用賽事後退出。")
    parser.add_argument("--status", action="store_true", help="顯示 pipeline 狀態後退出。")
    parser.add_argument("--compile-only", action="store_true", help="只執行最終 SGM 編譯。")
    parser.add_argument("--auto", action="store_true",
                        help="自動模式 — 跳過確認閘門，用於 NEXT_CMD 循環。")
    parser.add_argument("--skip-extractor", action="store_true",
                        help="跳過 nba_extractor.py（用 Sportsbet fallback）。")
    args = parser.parse_args()

    if not args.date:
        args.date = datetime.datetime.now().strftime("%Y-%m-%d")

    print("=" * 60)
    print("🏀 NBA Wong Choi Pipeline Orchestrator V3")
    print(f"📅 目標日期: {args.date}")
    if args.game:
        print(f"🎯 指定賽事: {args.game}")
    if args.auto:
        print(f"⚡ 自動模式 (NEXT_CMD)")
    print("=" * 60)

    # ── Preflight ──
    if not preflight_check():
        sys.exit(1)

    target_dir = get_target_dir(args.date)
    print(f"📁 目標目錄: {target_dir}\n")

    # ── Phase 0: Sportsbet Odds Crawling ──
    json_files = discover_sportsbet_jsons(target_dir)
    if not json_files:
        print("🚨 Phase 0: 缺少 Sportsbet JSON 盤口數據！啟動 Claw 抓取...")
        claw_ok = run_script(CLAW_SPORTSBET, ["--outdir", target_dir], label="Claw Sportsbet")
        if not claw_ok:
            print("❌ [Fatal] Claw 執行失敗！可能 Cloudflare 阻擋或當日無賽事。")
            sys.exit(1)
        json_files = discover_sportsbet_jsons(target_dir)
        if not json_files:
            print("❌ [Fatal] 爬蟲執行後仍無 Sportsbet JSON！")
            sys.exit(1)

    # Build game list
    games = []
    for jf in json_files:
        tag = extract_game_tag(jf)
        games.append({"tag": tag, "sportsbet_json": jf})

    print(f"✅ 成功載入 {len(games)} 場賽事盤口數據:")
    for i, g in enumerate(games, 1):
        print(f"   {i}. {g['tag']}")

    # ── --list mode ──
    if args.list:
        print(f"\n可用賽事 tags: {[g['tag'] for g in games]}")
        print("使用 --game <TAG> 來分析指定賽事。")
        sys.exit(0)

    # ── --status mode ──
    if args.status:
        print_status(target_dir, [g["tag"] for g in games])
        sys.exit(0)

    # ── --compile-only mode ──
    if args.compile_only:
        game_tags = [g["tag"] for g in games]
        if os.path.exists(GENERATE_SGM):
            run_script(GENERATE_SGM, ["--dir", target_dir], label="SGM Master Report")
            write_state(target_dir, game_tags, "compile_complete")
        else:
            print(f"❌ 找不到 SGM 報告生成器: {GENERATE_SGM}")
        sys.exit(0)

    # ── Filter to single game if --game specified ──
    if args.game:
        game_filter = args.game.upper().replace(" ", "_").replace("@", "_")
        filtered = [g for g in games if game_filter in g["tag"] or g["tag"] in game_filter]
        if not filtered:
            print(f"\n❌ 找不到賽事: '{args.game}'")
            print(f"   可用: {[g['tag'] for g in games]}")
            sys.exit(1)
        games = filtered
        print(f"\n🎯 已過濾至 {len(games)} 場: {[g['tag'] for g in games]}")

    # ── Per-Game Pipeline ──
    results = {"passed": [], "failed": []}

    for idx, game in enumerate(games, 1):
        tag = game["tag"]
        sb_json = game["sportsbet_json"]
        success = process_single_game(
            tag, sb_json, target_dir, args.date,
            game_num=idx, skip_extractor=args.skip_extractor
        )
        if success:
            results["passed"].append(tag)
        else:
            results["failed"].append(tag)

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"🏆 Pipeline 執行摘要")
    print(f"{'='*60}")
    print(f"✅ 通過: {len(results['passed'])} 場 — {results['passed']}")
    if results["failed"]:
        print(f"❌ 失敗: {len(results['failed'])} 場 — {results['failed']}")

    # ── SGM + Banker Report ──
    if len(results["passed"]) >= 2 and os.path.exists(GENERATE_SGM):
        print(f"\n📋 生成 Master SGM + Banker 報告...")
        run_script(GENERATE_SGM, ["--dir", target_dir], label="SGM Master Report")

    # ── State persistence ──
    write_state(target_dir, [g["tag"] for g in games], "pipeline_complete")

    # ── Status ──
    print_status(target_dir, [g["tag"] for g in games])

    # ── NEXT_CMD for auto-loop (state-aware) ──
    if results["failed"]:
        print(f"\n⚠️ {len(results['failed'])} 場失敗。修復後可重跑。")

    fill_count = _count_fill_residuals(target_dir)
    if fill_count > 0:
        # Phase 2: LLM needs to fill [FILL] fields
        print(f"\n📋 [Phase 2] 有 {fill_count} 個 [FILL] 需要 LLM 填寫。")
        print(f"  👉 讀取每份 Game_*_Full_Analysis.md 並填寫 [FILL] 欄位")
        print(f"  🔒 嚴禁修改 Python 預填嘅數學數據")
        print(f"  完成後重新執行 orchestrator:")
        _next_cmd(args.date, "--compile-only")
    elif len(results["passed"]) >= 2 and not os.path.exists(
        os.path.join(target_dir, "NBA_All_SGM_Report.txt")
    ):
        # Phase 3: Compile needed
        print(f"\n📋 所有報告已完成，需要編譯 SGM 匯總。")
        _next_cmd(args.date, "--compile-only")
    else:
        # Pipeline fully complete — no NEXT_CMD
        print(f"\n🎉 Pipeline 完全完成！無需進一步操作。")

    print(f"\n🎯 [Orchestrator V3] Pipeline 完成！")
    print(f"所有報告位於: {target_dir}")
    sys.exit(0)


if __name__ == "__main__":
    main()