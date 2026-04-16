#!/usr/bin/env python3
from __future__ import annotations
"""
⚠️ DEPRECATED — USE .agents/skills/nba/nba_orchestrator.py (V3) INSTEAD.

This file is kept for reference only. The canonical orchestrator is now
the unified V3 at: .agents/skills/nba/nba_orchestrator.py

nba_orchestrator.py — NBA Wong Choi Pipeline Controller V9 [DEPRECATED]

  Phase 1A: generate_nba_auto.py    → nba_game_data_{TAG}.json (L10 from nba_api)
  Phase 1B: generate_nba_reports.py → Game_{TAG}_Skeleton.md   (pre-filled report)
  Phase 2:  LLM Analyst fills [FILL] fields only
  Phase 3:  compile_nba_report.py   → Banker_Combinations.txt + Master_SGM.txt

Usage:
  python3 nba_orchestrator.py --dir "2026-04-15 NBA Analysis"
  python3 nba_orchestrator.py --dir "2026-04-15 NBA Analysis" --games MIA_CHA POR_PHX
  python3 nba_orchestrator.py --dir "2026-04-15 NBA Analysis" --compile-only
  python3 nba_orchestrator.py --dir "2026-04-15 NBA Analysis" --status
"""

import os
import sys
import argparse
import subprocess
import datetime
import glob
import json
import re

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPT_DIR)))

# Path to the EXISTING 1325-line report generator
REPORT_GENERATOR = os.path.join(
    BASE_DIR, ".agents", "skills", "nba", "nba_wong_choi", "scripts", "generate_nba_reports.py"
)
# Path to the extractor data generator
DATA_GENERATOR = os.path.join(BASE_DIR, "generate_nba_auto.py")
# Path to the compiler
COMPILER = os.path.join(_SCRIPT_DIR, "compile_nba_report.py")


# ──────────────────────────────────────────────────────────────────────────
# Discovery & Filtering
# ──────────────────────────────────────────────────────────────────────────

def discover_sportsbet_files(target_dir: str) -> list:
    files = glob.glob(os.path.join(target_dir, "Sportsbet_Odds_*.json"))
    return sorted(f for f in files
                  if "TEST" not in f and "MIN" not in f and "GEMINI" not in f)


def extract_game_tag(sb_path: str) -> str:
    base = os.path.basename(sb_path)
    return base.replace("Sportsbet_Odds_", "").replace(".json", "")


def detect_todays_games(target_dir: str) -> list | None:
    """Try to read NBA_Data_Package_Auto_Fixed.md to find today's actual games."""
    pkg = os.path.join(target_dir, "NBA_Data_Package_Auto_Fixed.md")
    if not os.path.exists(pkg):
        return None
    try:
        with open(pkg, "r", encoding="utf-8") as f:
            content = f.read()
        # Extract game tags like (MIA_CHA) from the package
        tags = re.findall(r'\(([A-Z]{2,3}_[A-Z]{2,3})\)', content)
        return tags if tags else None
    except Exception:
        return None


def filter_games(sb_files: list, game_filter: list | None) -> list:
    """Filter Sportsbet files to only include specified game tags."""
    if not game_filter:
        return sb_files
    filtered = []
    for sb in sb_files:
        tag = extract_game_tag(sb)
        if tag in game_filter:
            filtered.append(sb)
    return filtered


# ──────────────────────────────────────────────────────────────────────────
# Phase 1A: Generate Extractor JSONs
# ──────────────────────────────────────────────────────────────────────────

def run_phase_1a(target_dir: str, game_tags: list):
    """Run generate_nba_auto.py to produce nba_game_data_{TAG}.json files."""
    if not os.path.exists(DATA_GENERATOR):
        print(f"❌ [Fatal] 找不到: {DATA_GENERATOR}")
        sys.exit(1)

    print(f"\n🚀 [Phase 1A] 生成 Extractor JSON (nba_api L10 Stats)...")
    cmd = ["python3", DATA_GENERATOR, "--dir", target_dir]
    if game_tags:
        cmd += ["--games"] + game_tags

    try:
        subprocess.run(cmd, check=True)
        print("✅ [Phase 1A] Extractor JSON 生成完成！")
    except subprocess.CalledProcessError as exc:
        print(f"❌ [Phase 1A Error] {exc}")
        sys.exit(1)


def verify_phase_1a(target_dir: str, game_tags: list) -> list:
    """Check that extractor JSONs exist."""
    missing = []
    for tag in game_tags:
        path = os.path.join(target_dir, f"nba_game_data_{tag}.json")
        if not os.path.exists(path):
            missing.append(f"nba_game_data_{tag}.json")
    return missing


# ──────────────────────────────────────────────────────────────────────────
# Phase 1B: Generate Skeleton MDs via generate_nba_reports.py
# ──────────────────────────────────────────────────────────────────────────

def run_phase_1b(target_dir: str, game_tags: list):
    """Run generate_nba_reports.py for each game to produce Skeleton MDs."""
    if not os.path.exists(REPORT_GENERATOR):
        print(f"❌ [Fatal] 找不到報告生成器: {REPORT_GENERATOR}")
        print(f"   預期位置: .agents/skills/nba/nba_wong_choi/scripts/generate_nba_reports.py")
        sys.exit(1)

    print(f"\n🚀 [Phase 1B] 生成 Skeleton MD (Pre-filled Reports)...")

    for tag in game_tags:
        sb_path = os.path.join(target_dir, f"Sportsbet_Odds_{tag}.json")
        ext_path = os.path.join(target_dir, f"nba_game_data_{tag}.json")
        out_path = os.path.join(target_dir, f"Game_{tag}_Full_Analysis.md")

        if not os.path.exists(sb_path):
            print(f"  ⚠️ Skip {tag}: Sportsbet JSON 唔存在")
            continue
        if not os.path.exists(ext_path):
            print(f"  ⚠️ Skip {tag}: Extractor JSON 唔存在 (Phase 1A 可能失敗)")
            continue

        print(f"  📄 {tag}: generate_nba_reports.py ... ", end="", flush=True)
        try:
            subprocess.run([
                "python3", REPORT_GENERATOR,
                "--sportsbet", sb_path,
                "--extractor", ext_path,
                "--output", out_path,
            ], check=True, capture_output=True, text=True)
            print("✅")
        except subprocess.CalledProcessError as exc:
            print(f"❌")
            print(f"    Error: {exc.stderr[:300] if exc.stderr else exc}")

    print("✅ [Phase 1B] Skeleton 生成完成！")


def verify_phase_1b(target_dir: str, game_tags: list) -> list:
    """Check that skeleton MDs exist."""
    missing = []
    for tag in game_tags:
        path = os.path.join(target_dir, f"Game_{tag}_Full_Analysis.md")
        if not os.path.exists(path):
            missing.append(f"Game_{tag}_Full_Analysis.md")
    return missing


# ──────────────────────────────────────────────────────────────────────────
# Phase 3: Compile Reports
# ──────────────────────────────────────────────────────────────────────────

def run_phase_3(target_dir: str):
    if not os.path.exists(COMPILER):
        print(f"❌ [Fatal] 找不到: {COMPILER}")
        sys.exit(1)

    analyses = glob.glob(os.path.join(target_dir, "Game_*_Full_Analysis.md"))
    if not analyses:
        print("⚠️ [Phase 3] 未找到 Game_*_Full_Analysis.md — 請先完成 Phase 1")
        return False

    print(f"\n🚀 [Phase 3] 編譯匯總報告 ({len(analyses)} 份分析)...")
    try:
        subprocess.run(
            ["python3", COMPILER, "--target_dir", target_dir],
            check=True,
        )
        print("✅ [Phase 3] 報告編譯完成！")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"❌ [Phase 3 Error] {exc}")
        return False


# ──────────────────────────────────────────────────────────────────────────
# Status Report
# ──────────────────────────────────────────────────────────────────────────

def print_status(target_dir: str, game_tags: list):
    print(f"\n📋 Pipeline 狀態 ({os.path.relpath(target_dir)})")
    print(f"{'─'*50}")
    for tag in game_tags:
        sb = "✅" if os.path.exists(os.path.join(target_dir, f"Sportsbet_Odds_{tag}.json")) else "❌"
        ext = "✅" if os.path.exists(os.path.join(target_dir, f"nba_game_data_{tag}.json")) else "❌"
        skel = "✅" if os.path.exists(os.path.join(target_dir, f"Game_{tag}_Full_Analysis.md")) else "❌"
        print(f"  {tag}: Odds {sb} | Extractor {ext} | Analysis {skel}")

    bk = "✅" if os.path.exists(os.path.join(target_dir, "Banker_Combinations.txt")) else "❌"
    sg = "✅" if os.path.exists(os.path.join(target_dir, "Master_SGM.txt")) else "❌"
    print(f"\n  匯總: Banker {bk} | SGM {sg}")


# ──────────────────────────────────────────────────────────────────────────
# State persistence
# ──────────────────────────────────────────────────────────────────────────

def write_state(target_dir: str, game_tags: list, phase: str):
    state_file = os.path.join(target_dir, "_nba_session_state.md")
    now = datetime.datetime.now().isoformat()
    with open(state_file, "a", encoding="utf-8") as fh:
        fh.write(f"\n🔒 NBA_ORCHESTRATOR: {phase.upper()} | {now}\n")
        fh.write(f"   Games: {', '.join(game_tags)}\n")


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NBA Orchestrator V9 — Full Pipeline Controller")
    parser.add_argument("--dir", default=".", help="Target directory with Sportsbet JSONs")
    parser.add_argument("--games", nargs="*", default=None,
                        help="Specific game tags (e.g. MIA_CHA POR_PHX). "
                             "Auto-detects from NBA_Data_Package if omitted.")
    parser.add_argument("--compile-only", action="store_true",
                        help="Skip Phase 1, run Phase 3 compile only")
    parser.add_argument("--status", action="store_true",
                        help="Show pipeline status and exit")
    parser.add_argument("--all-games", action="store_true",
                        help="Process ALL Sportsbet files (ignore date filtering)")
    args = parser.parse_args()

    target_dir = os.path.abspath(args.dir)
    print(f"🌐 [Orchestrator V9] 目標: {os.path.relpath(target_dir)}")

    # ── Discover games ───────────────────────────────────────────────────
    sb_files = discover_sportsbet_files(target_dir)
    if not sb_files:
        print(f"❌ 找不到 Sportsbet_Odds_*.json 於 {target_dir}")
        sys.exit(1)

    all_tags = [extract_game_tag(f) for f in sb_files]

    # ── Game filtering (priority: CLI args > Auto-detect > all) ──────────
    if args.games:
        game_tags = args.games
        print(f"🎯 手動指定場次: {', '.join(game_tags)}")
    elif not args.all_games:
        auto_tags = detect_todays_games(target_dir)
        if auto_tags:
            game_tags = auto_tags
            print(f"🎯 自動偵測到賽程 ({len(auto_tags)} 場): {', '.join(game_tags)}")
            # Warn about extra files
            extra = set(all_tags) - set(auto_tags)
            if extra:
                print(f"   ⚠️ 忽略 {len(extra)} 個非今日場次: {', '.join(sorted(extra))}")
        else:
            game_tags = all_tags
            print(f"   ⚠️ 無法偵測賽程 (NBA_Data_Package 唔存在)，處理全部 {len(all_tags)} 場")
    else:
        game_tags = all_tags

    sb_files = filter_games(sb_files, game_tags)
    print(f"✅ 目標場次 ({len(game_tags)}): {', '.join(game_tags)}")

    # ── Status only ──────────────────────────────────────────────────────
    if args.status:
        print_status(target_dir, game_tags)
        return

    # ── Compile-only ─────────────────────────────────────────────────────
    if args.compile_only:
        success = run_phase_3(target_dir)
        if success:
            write_state(target_dir, game_tags, "compile_complete")
        return

    # ── Phase 1A: Generate Extractor JSONs ───────────────────────────────
    run_phase_1a(target_dir, game_tags)
    missing = verify_phase_1a(target_dir, game_tags)
    if missing:
        print(f"\n🚨 [Phase 1A Gate] 缺少: {missing}")
        sys.exit(1)
    print(f"✅ [Phase 1A Gate] 所有 Extractor JSON 已就緒")

    # ── Phase 1B: Generate Skeleton MDs ──────────────────────────────────
    run_phase_1b(target_dir, game_tags)
    missing = verify_phase_1b(target_dir, game_tags)
    if missing:
        print(f"\n⚠️ [Phase 1B] 部分 Skeleton 生成失敗: {missing}")
        print("   Pipeline 將繼續處理成功嘅場次。")

    # ── Phase 2 Instructions ─────────────────────────────────────────────
    skeletons = glob.glob(os.path.join(target_dir, "Game_*_Full_Analysis.md"))
    fill_count = 0
    for sk in skeletons:
        with open(sk, "r", encoding="utf-8") as f:
            fill_count += f.read().count("[FILL]")

    if fill_count > 0:
        print(f"\n{'='*60}")
        print(f"📋 [Phase 2] LLM Analyst 填充指令")
        print(f"{'='*60}")
        print(f"  📄 已生成 {len(skeletons)} 份 Skeleton (含 {fill_count} 個 [FILL])")
        print(f"  👉 LLM 只需讀取每份 Skeleton 並填寫 [FILL] 欄位")
        print(f"  🔒 嚴禁修改 Python 預填嘅數學數據")
        print(f"\n  完成後執行:")
        print(f"  python3 .agents/scripts/nba/nba_orchestrator.py --dir \"{os.path.relpath(target_dir)}\" --compile-only")
    else:
        print(f"\n🎉 Skeleton 已生成且無 [FILL] — 直接觸發 Phase 3")
        run_phase_3(target_dir)

    write_state(target_dir, game_tags, "phase1_complete")

    # Final status
    print_status(target_dir, game_tags)

    print(f"\n🎯 [Orchestrator V9] Pipeline 就緒！")


if __name__ == "__main__":
    main()
