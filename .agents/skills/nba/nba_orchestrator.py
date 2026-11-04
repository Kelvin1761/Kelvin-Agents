#!/usr/bin/env python3
from __future__ import annotations
import os
import re
from pathlib import Path
os.environ.setdefault('PYTHONUTF8', '1')
"""
nba_orchestrator.py — NBA Wong Choi pipeline orchestrator
==========================================================
Pipeline (per game, in parallel):
  Phase 0:  claw_sportsbet_odds.py  → Sportsbet_Odds_{TAG}.json
  Phase 1A: nba_extractor.py        → nba_game_data_{TAG}.json (ESPN only)
  Phase 1B: nba_engine/run.py       → Game_{TAG}_Full_Analysis.md + .market_legs.json
  Firewall: validate_nba_output.py  (nba_engine.publish)
  Phase 3:  generate_nba_sgm_reports.py → NBA_All_SGM_Report.txt + NBA_Banker_Report.txt

Usage:
  python nba_orchestrator.py --date 2026-04-16
  python nba_orchestrator.py --date 2026-04-16 --game ATL_NYK
  python nba_orchestrator.py --date 2026-04-16 --list
  python nba_orchestrator.py --date 2026-04-16 --status
  python nba_orchestrator.py --date 2026-04-16 --compile-only
  python nba_orchestrator.py --date 2026-04-16 --auto   # what the scheduler runs (--auto is a no-op)
"""
import argparse
import datetime
import glob
import hashlib
import json
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nba_availability import availability_current

# ─── Cross-Platform Python ──────────────────────────────────────────────
PYTHON = sys.executable

# ─── Path Constants ─────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
SKILLS_DIR = SCRIPT_DIR  # .agents/skills/nba/

CLAW_SPORTSBET = os.path.join(SKILLS_DIR, "nba_data_extractor", "scripts", "claw_sportsbet_odds.py")
NBA_EXTRACTOR = os.path.join(SKILLS_DIR, "nba_data_extractor", "scripts", "nba_extractor.py")
ENGINE_DIR = os.path.join(SKILLS_DIR, "nba_engine")
GENERATE_REPORTS = os.path.join(ENGINE_DIR, "run.py")
VALIDATE_OUTPUT = os.path.join(SKILLS_DIR, "nba_wong_choi", "scripts", "validate_nba_output.py")
GENERATE_SGM = os.path.join(SKILLS_DIR, "nba_wong_choi", "scripts", "generate_nba_sgm_reports.py")
SHARED_HOOK_DIR = os.path.join(
    WORKSPACE_ROOT, ".agents", "skills", "shared_racing", "post_success_hooks", "scripts"
)
sys.path.insert(0, SHARED_HOOK_DIR)
from cloudflare_deploy_hook import run_post_success_cloudflare_deploy

sys.path.insert(0, SCRIPT_DIR)
from nba_schedule import canonical_game_tag, load_espn_schedule


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

def get_target_dir(date_str: str, *, create: bool = True) -> str:
    target_dir = os.path.join(WORKSPACE_ROOT, f"{date_str} NBA Analysis")
    if create:
        os.makedirs(target_dir, exist_ok=True)
    return target_dir


def run_script(
    script_path: str,
    args_list: list,
    label: str = "Script",
    timeout: int = 1800,
    failure_codes: list[int] | None = None,
    success_codes: tuple[int, ...] = (0,),
) -> bool:
    if not os.path.exists(script_path):
        if failure_codes is not None:
            failure_codes.append(75)
        print(f"❌ [{label}] 找不到腳本: {script_path}")
        return False
    cmd = [PYTHON, script_path] + args_list
    print(f"🔧 [{label}] 執行: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.stdout:
            # Show last 500 chars to avoid flooding terminal
            output = result.stdout.strip()
            if len(output) > 500:
                print(f"   ...{output[-500:]}")
            else:
                print(f"   {output}")
        return True
    except subprocess.CalledProcessError as e:
        if e.returncode in success_codes:
            print(f"⚠️ [{label}] 通過，有警告 (exit code: {e.returncode})")
            if e.stdout:
                print(e.stdout[-4000:])
            return True
        if failure_codes is not None:
            failure_codes.append(e.returncode)
        print(f"⚠️ [{label}] 執行失敗 (exit code: {e.returncode})")
        if e.stdout:
            print(f"   stdout: {e.stdout[-4000:]}")
        if e.stderr:
            print(f"   stderr: {e.stderr[-2000:]}")
        return False
    except subprocess.TimeoutExpired:
        if failure_codes is not None:
            failure_codes.append(75)
        print(f"⏱️ [{label}] 超過 {timeout} 秒，已停止並當作失敗。")
        return False


def discover_sportsbet_jsons(target_dir: str) -> list:
    pattern = os.path.join(target_dir, "Sportsbet_Odds_*.json")
    return sorted(f for f in glob.glob(pattern)
                  if "TEST" not in f and "GEMINI" not in f)


def extract_game_tag(json_path: str) -> str:
    filename = os.path.basename(json_path)
    return canonical_game_tag(
        filename.replace("Sportsbet_Odds_", "").replace(".json", "")
    )


def _load_espn_tags(date_str: str) -> set[str]:
    """Backward-compatible tag-only wrapper used by the main pipeline."""
    return load_espn_schedule(date_str)[0]


def filter_sportsbet_files_by_date(files: list[str], target_tags: set[str]) -> list[str]:
    if not target_tags:
        return files
    filtered = []
    for path in files:
        if extract_game_tag(path) in target_tags:
            filtered.append(path)
    return filtered


def _load_sportsbet_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def player_milestone_markets_available(payload: dict) -> bool:
    """Require at least one priced, supported player milestone; game lines alone are insufficient."""
    props = payload.get("player_props") or {}
    if not isinstance(props, dict):
        return False
    for category in ("points", "rebounds", "assists", "threes_made"):
        players = props.get(category) or {}
        if not isinstance(players, dict):
            continue
        for player in players.values():
            if not isinstance(player, dict) or not isinstance(player.get("lines"), dict):
                continue
            for line, price in player["lines"].items():
                try:
                    threshold, odds = float(line), float(price)
                    if threshold > 0 and threshold.is_integer() and 1 < odds < float("inf"):
                        return True
                except (TypeError, ValueError):
                    continue
    return False


def sportsbet_json_matches_target(path: str, target_date: str, target_tags: set[str]) -> bool:
    payload = _load_sportsbet_json(path)
    inferred_tag = extract_game_tag(path)
    payload_tag = canonical_game_tag(payload.get("matchup", ""))
    effective_tag = payload_tag or inferred_tag

    explicit_dates = [
        value
        for value in (
            payload.get("target_analysis_date"),
            payload.get("event_local_date"),
        )
        if value
    ]
    if explicit_dates:
        if any(value != target_date for value in explicit_dates):
            return False
        if target_tags and effective_tag not in target_tags:
            return False
        return True

    # Older JSON without explicit date metadata is unsafe for strict date requests.
    return False


def filter_sportsbet_files_for_target(files: list[str], target_date: str, target_tags: set[str]) -> list[str]:
    return [path for path in files if sportsbet_json_matches_target(path, target_date, target_tags)]


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


def validate_reports_for_release(target_dir: str, game_tags=None) -> bool:
    reports = ([os.path.join(target_dir, f"Game_{tag}_Full_Analysis.md") for tag in game_tags]
               if game_tags is not None else sorted(glob.glob(os.path.join(target_dir, "Game_*_Full_Analysis.md"))))
    if not reports:
        print("⛔ 冇任何 Game_*_Full_Analysis.md 可供編譯。")
        return False
    if any(not os.path.isfile(report) for report in reports):
        print("⛔ 指定賽事缺少分析報告。")
        return False
    if not os.path.exists(VALIDATE_OUTPUT):
        print(f"⛔ 防火牆 validator 不存在: {VALIDATE_OUTPUT}")
        return False
    return all(
        run_script(VALIDATE_OUTPUT, [report], label="Compile Release Validator", success_codes=(0, 2))
        for report in reports
    )


def _release_action(*, passed: bool, failed: bool, sgm_ok: bool) -> str:
    """Deploy only when every game passed and the SGM summary was written."""
    return "deploy" if passed and not failed and sgm_ok else "blocked"


# ─── Per-Game Pipeline ──────────────────────────────────────────────────

def extractor_cache_current(path: str) -> bool:
    """Invalidate preseason caches produced before rookies were retained."""
    try:
        with open(path, encoding="utf-8") as source:
            payload = json.load(source)
        meta = payload.get("meta", {})
        from nba_data_contract import statistics_current
        if not statistics_current(meta):
            return False
        groups = payload.get("players", {})
        if not isinstance(groups, dict):
            return False
        for group in groups.values():
            if not isinstance(group, list) or any(
                not isinstance(player, dict) or not isinstance(player.get("position", ""), str)
                for player in group
            ):
                return False
        if meta.get("season_phase") == "PRESEASON":
            return meta.get("preseason_rookie_history_contract") == 1
        # Regular season: a cache written while team_stats / advanced data came
        # back empty (opening night 2026-10-21, before the season fallback) must
        # be re-extracted, otherwise the report keeps the "Pace／防守缺失" label.
        # EVERY team must have data, not just one: 2026-10-23 CLE_PHI / DEN_OKC cached
        # with the away team's team_stats and advanced both empty (the other team was
        # fine), passed the old "any team has data" test, and were never re-extracted.
        # The report then said "對手球隊數據為空" and found no combos for the game.
        team_stats = payload.get("team_stats")
        if isinstance(team_stats, dict) and any(not value for value in team_stats.values()):
            return False
        for group in groups.values():
            if group and not any(player.get("advanced") for player in group):
                return False
        return True
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def _file_digest(path: str) -> str:
    with open(path, "rb") as source:
        return hashlib.sha256(source.read()).hexdigest()


def report_inputs(sportsbet_json: str, extractor_json: str) -> dict:
    """What a report depends on: both input files and every engine source file."""
    engine = {name: _file_digest(os.path.join(ENGINE_DIR, name))
              for name in sorted(os.listdir(ENGINE_DIR)) if name.endswith((".py", ".json"))}
    inputs = {"schema_version": 3, "sportsbet": _file_digest(sportsbet_json),
              "extractor": _file_digest(extractor_json), "engine": engine}
    revision = subprocess.run(
        ["git", "-C", WORKSPACE_ROOT, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    inputs["code_revision"] = revision.stdout.strip() if revision.returncode == 0 else None
    return inputs


def _publishable(report: str, sportsbet_json: str) -> bool:
    from nba_engine.publish import validate
    return validate(report, sportsbet_json)[0]


def report_quotes_current(report: str, sportsbet_json: str) -> bool:
    """The report passes the publication firewall now, after renewing expired quotes
    whose price is unchanged."""
    from nba_sgm_quote import requote_sidecar
    if _publishable(report, sportsbet_json):
        return True
    try:
        odds = json.loads(Path(sportsbet_json).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return requote_sidecar(report, odds) and _publishable(report, sportsbet_json)


def report_cache_current(report: str, sportsbet_json: str, extractor_json: str) -> bool:
    try:
        with open(report + ".inputs.json", encoding="utf-8") as source:
            cached = json.load(source)
        # Inputs first: a report that must be regenerated is not worth a quote request.
        return (cached.get("inputs") == report_inputs(sportsbet_json, extractor_json)
                and cached.get("report") == _file_digest(report)
                and report_quotes_current(report, sportsbet_json))
    except (OSError, ValueError, AttributeError):
        return False


def process_single_game(game_tag: str, sportsbet_json: str, target_dir: str,
                        date_str: str, game_num: int | None = None) -> bool:
    prefix = f"Game {game_num}" if game_num else game_tag
    print(f"\n{'='*60}")
    print(f"🏀 [{prefix}] {game_tag} — 開始 Pipeline")
    print(f"{'='*60}")

    if not player_milestone_markets_available(_load_sportsbet_json(sportsbet_json)):
        print(f"⏳ [{prefix}] player_markets_not_open：未有可分析球員里程碑盤口，保留重試，唔生成分析或 snapshot。")
        return False

    extractor_json = os.path.join(target_dir, f"nba_game_data_{game_tag}.json")
    availability_ready = False
    if os.path.isfile(extractor_json) and extractor_cache_current(extractor_json):
        with open(extractor_json, encoding="utf-8") as source:
            availability_ready = availability_current(json.load(source))
        if not availability_ready:
            refresh_failures = []
            refreshed = run_script(NBA_EXTRACTOR, ["--refresh-availability", extractor_json],
                                   label=f"{prefix} Availability Refresh", failure_codes=refresh_failures)
            if refreshed:
                with open(extractor_json, encoding="utf-8") as source:
                    availability_ready = availability_current(json.load(source))
                if not availability_ready:
                    print(f"⛔ [{prefix}] availability refresh 冇產生可驗證資料，唔重用舊報告。")
                    return False
            elif refresh_failures != [2]:
                print(f"⛔ [{prefix}] 傷停來源失敗或賽事已開始，保留原檔等重試。")
                return False

    # ── Check if already completed ──
    existing = check_skeleton_exists(target_dir, game_tag)
    if existing and availability_ready and extractor_cache_current(extractor_json) and report_cache_current(
        existing, sportsbet_json, extractor_json,
    ):
        print(f"✅ [{prefix}] 已存在合格報告: {os.path.basename(existing)} ({os.path.getsize(existing)} bytes)")
        if os.path.exists(VALIDATE_OUTPUT):
            validate_ok = run_script(VALIDATE_OUTPUT, [existing], label=f"{prefix} Existing Report Validator", success_codes=(0, 2))
            if not validate_ok:
                print(f"⛔ [{prefix}] 現有報告防火牆未通過，唔可以當完成。")
                return False
        print(f"   驗證通過，安全重用。")
        return True

    # ── Phase 1A: nba_extractor.py (球員深度數據) ──
    ext_date = date_str.replace("-", "")
    if availability_ready and os.path.exists(extractor_json) and extractor_cache_current(extractor_json):
        print(f"✅ [{prefix}] Extractor JSON 已存在: {os.path.basename(extractor_json)}")
    else:
        print(f"\n📡 [{prefix}] Phase 1A: 執行 nba_extractor.py 提取球員數據...")
        extractor_ok = run_script(NBA_EXTRACTOR, [
            "--date", ext_date,
            "--game", game_tag,
            "--output", extractor_json
        ], label=f"{prefix} Extractor")

        if not extractor_ok or not os.path.exists(extractor_json):
            print(f"❌ [{prefix}] nba_extractor.py 失敗！無 L10 數據。")
            print(f"   可能原因: ESPN 唔通／熔斷中 / ESPN 日期轉換問題")
            print(f"   ⛔ 跳過此賽事 — 冇真實 L10 gamelog 不進行分析。")
            return False

    from nba_data_contract import statistics_current
    with open(extractor_json, encoding="utf-8") as source:
        current_payload = json.load(source)
    if not statistics_current(current_payload.get("meta")):
        print(f"⛔ [{prefix}] 統計來源失敗或單位未驗證，保留重試，唔發布。")
        return False
    if not availability_current(current_payload):
        print(f"⛔ [{prefix}] 傷停／陣容未驗證或已過期，保留重試，唔發布。")
        return False

    # ── Phase 1B: nba_engine (Full Analysis + sidecar) ──
    analysis_md = os.path.join(target_dir, f"Game_{game_tag}_Full_Analysis.md")
    print(f"\n📊 [{prefix}] Phase 1B: 執行 nba_engine 生成分析報告...")
    _report_args = [
        "--sportsbet", sportsbet_json,
        "--extractor", extractor_json,
        "--output", analysis_md,
    ]
    try:
        inputs_before = report_inputs(sportsbet_json, extractor_json)
    except OSError as exc:
        print(f"⛔ [{prefix}] 無法核對報告輸入：{exc}")
        return False
    report_ok = run_script(GENERATE_REPORTS, _report_args, label=f"{prefix} Report Generator")

    if not report_ok or not os.path.exists(analysis_md):
        print(f"❌ [{prefix}] 分析報告生成失敗！")
        return False

    analysis_size = os.path.getsize(analysis_md)
    print(f"✅ [{prefix}] 分析報告已生成: {os.path.basename(analysis_md)} ({analysis_size} bytes)")

    if analysis_size < 2000:
        print(f"⚠️ [{prefix}] 報告大小偏小 ({analysis_size} bytes)，可能數據不足。")

    # ── Validation (防火牆) ──
    if os.path.exists(VALIDATE_OUTPUT):
        # A slow generation under parallel load can outlive the quote it took.
        report_quotes_current(analysis_md, sportsbet_json)
        print(f"\n🛡️ [{prefix}] Validation: 執行 validate_nba_output.py...")
        validate_ok = run_script(VALIDATE_OUTPUT, [analysis_md], label=f"{prefix} Validator", success_codes=(0, 2))
        if not validate_ok:
            print(f"⛔ [{prefix}] 防火牆檢查未通過，唔可以發布。")
            return False

    try:
        if report_inputs(sportsbet_json, extractor_json) != inputs_before:
            print(f"⛔ [{prefix}] 報告生成期間輸入已改變，保留重試，唔發布。")
            return False
        cache_path = analysis_md + ".inputs.json"
        temporary = cache_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as cache:
            json.dump({"inputs": inputs_before, "report": _file_digest(analysis_md)}, cache)
        os.replace(temporary, cache_path)
    except OSError as exc:
        print(f"⛔ [{prefix}] 無法保存報告輸入核對：{exc}")
        return False

    print(f"\n🎉 [{prefix}] {game_tag} Pipeline 完成！")
    return True


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
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(
        description="NBA Wong Choi pipeline: Sportsbet → ESPN extractor → nba_engine → firewall → SGM summary"
    )
    parser.add_argument("--date", help="分析日期 (YYYY-MM-DD)。預設為今日。")
    parser.add_argument("--game", help="只分析指定賽事 (e.g., ATL_NYK)。")
    parser.add_argument("--list", action="store_true", help="列出可用賽事後退出。")
    parser.add_argument("--status", action="store_true", help="顯示 pipeline 狀態後退出。")
    parser.add_argument("--compile-only", action="store_true", help="只執行最終 SGM 編譯。")
    parser.add_argument("--games", nargs="+", help="Compile-only 指定多個已驗證賽事。")
    parser.add_argument("--auto", action="store_true",
                        help="接受但冇作用：排程一直傳呢個 flag（舊 NEXT_CMD 循環）。")
    parser.add_argument("--workers", type=int,
                        default=int(os.environ.get("NBA_PIPELINE_WORKERS", "3")),
                        help="同時處理幾場賽事（預設 3；1 = 串行）。")
    parser.add_argument("--skip-cloudflare-deploy", action="store_true",
                        help="完成分析後唔更新 Cloudflare Dashboard。")
    args = parser.parse_args()

    if args.games and (not args.compile_only or args.game):
        parser.error("--games requires --compile-only and cannot be combined with --game")
    if args.games and any(not re.fullmatch(r"[A-Z]{2,4}_[A-Z]{2,4}", tag) for tag in args.games):
        parser.error("Invalid game tag")

    if not args.date:
        args.date = datetime.datetime.now().strftime("%Y-%m-%d")

    print("=" * 60)
    print("🏀 NBA Wong Choi Pipeline Orchestrator")
    print(f"📅 目標日期: {args.date}")
    if args.game:
        print(f"🎯 指定賽事: {args.game}")
    print("=" * 60)

    # ── Preflight ──
    if not preflight_check():
        sys.exit(1)

    target_dir = get_target_dir(
        args.date,
        create=not (args.status or args.compile_only),
    )
    print(f"📁 目標目錄: {target_dir}\n")

    # Compile-only is a local release operation. It must never crawl new odds,
    # and every report must pass the publication firewall again after edits.
    if args.compile_only:
        compile_games = args.games or ([args.game.upper()] if args.game else None)
        if not validate_reports_for_release(target_dir, compile_games):
            sys.exit(1)
        compile_args = ["--dir", target_dir] + (["--games", *compile_games] if compile_games else [])
        compile_ok = run_script(GENERATE_SGM, compile_args, label="SGM Master Report")
        sgm_exists = os.path.exists(os.path.join(target_dir, "NBA_All_SGM_Report.txt"))
        if not compile_ok or not sgm_exists:
            print("⛔ Compile-only 失敗；Dashboard 唔會更新。")
            sys.exit(1)
        write_state(target_dir, [], "compile_complete")
        run_post_success_cloudflare_deploy(
            source="NBA Wong Choi",
            target_dir=target_dir,
            skip=args.skip_cloudflare_deploy,
        )
        sys.exit(0)

    if args.status:
        local_tags = [extract_game_tag(path) for path in discover_sportsbet_jsons(target_dir)]
        print_status(target_dir, local_tags)
        sys.exit(0)

    expected_tags, schedule_reachable = load_espn_schedule(args.date)
    if not schedule_reachable:
        print("❌ [Fatal] ESPN 官方賽程來源不可用；為免錯日出牌，停止。")
        sys.exit(1)
    # ── Phase 0: Sportsbet Odds Crawling ──
    json_files = discover_sportsbet_jsons(target_dir)
    if json_files:
        verified_files = filter_sportsbet_files_for_target(json_files, args.date, expected_tags)
        rejected_count = len(json_files) - len(verified_files)
        if rejected_count:
            print(f"🧹 已排除 {rejected_count} 個 stale / 跨日 / 無法驗證日期嘅 Sportsbet JSON")
        json_files = verified_files

    if not json_files:
        print("🚨 Phase 0: 缺少可驗證屬於目標日期嘅 Sportsbet JSON！啟動 Claw 抓取...")
        claw_ok = run_script(CLAW_SPORTSBET, ["--outdir", target_dir, "--date", args.date], label="Claw Sportsbet")
        if not claw_ok:
            print("❌ [Fatal] Claw 執行失敗！可能 Cloudflare 阻擋或當日無賽事。")
            sys.exit(1)
        json_files = discover_sportsbet_jsons(target_dir)
        json_files = filter_sportsbet_files_for_target(json_files, args.date, expected_tags)
        if not json_files:
            print("❌ [Fatal] 爬蟲執行後仍無任何明確屬於目標日期嘅 Sportsbet JSON！")
            sys.exit(1)

    # Build game list
    games = []
    for jf in json_files:
        tag = extract_game_tag(jf)
        games.append({"tag": tag, "sportsbet_json": jf})

    print(f"✅ 成功載入 {len(games)} 場賽事盤口數據:")
    for i, g in enumerate(games, 1):
        print(f"   {i}. {g['tag']}")

    if not args.game:
        extracted_tags = {game["tag"] for game in games}
        missing = sorted(expected_tags - extracted_tags)
        unexpected = sorted(extracted_tags - expected_tags)
        if missing or unexpected:
            print(
                "⛔ 官方賽程覆蓋閘失敗："
                f"missing={missing or '[]'} unexpected={unexpected or '[]'}"
            )
            if missing and not unexpected:
                print("NBA_PIPELINE_RESULT: " + json.dumps({
                    "status": "waiting_game_markets",
                    "reason": "sportsbet_game_data_missing",
                    "waiting_games": missing,
                    "target_date": args.date,
                }, ensure_ascii=False))
                sys.exit(75)
            sys.exit(1)

    # ── --list mode ──
    if args.list:
        print(f"\n可用賽事 tags: {[g['tag'] for g in games]}")
        print("使用 --game <TAG> 來分析指定賽事。")
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
    results = {"passed": [], "failed": [], "waiting": []}

    # ⚠️ 逐場串行跑會超時：extractor 每場 ~6.5 分鐘（舊 nba_api 逐個 call 之間 sleep
    # 限流，大部分時間係等），7 場 slate 2026-10-26 要 61 分鐘，撞正 scheduler 嘅
    # 3600s 上限（最後一場 20:01:15 先完，limit 20:00:03）。各場只寫自己個
    # `*_{tag}.*` 檔，互不相干，所以用細 pool 並行。結果仍按場次次序收集。
    def _run_game(item):
        idx, game = item
        return process_single_game(game["tag"], game["sportsbet_json"], target_dir, args.date, game_num=idx)

    workers = max(1, min(args.workers, len(games) or 1))
    if workers == 1:
        outcomes = [_run_game(item) for item in enumerate(games, 1)]
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(_run_game, enumerate(games, 1)))

    for game, success in zip(games, outcomes):
        tag = game["tag"]
        sb_json = game["sportsbet_json"]
        if success:
            results["passed"].append(tag)
        else:
            results["failed"].append(tag)
            if not player_milestone_markets_available(_load_sportsbet_json(sb_json)):
                results["waiting"].append(tag)

    # The independently timestamped research audit is not rerun on quote refresh.
    # A long slate can outlive an early game's quote. Same-price quotes are
    # renewed in place (seconds); only a moved price or stale availability
    # regenerates a report (minutes), and that can expire the others again, so
    # every round re-checks the whole set right before release validation.
    for _ in range(3):
        stale = [game for game in games if game["tag"] in results["passed"] and not report_quotes_current(
            os.path.join(target_dir, f"Game_{game['tag']}_Full_Analysis.md"), game["sportsbet_json"])]
        if not stale:
            break
        for game in stale:
            tag = game["tag"]
            if not process_single_game(tag, game["sportsbet_json"], target_dir, args.date):
                results["passed"].remove(tag)
                results["failed"].append(tag)

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"🏆 Pipeline 執行摘要")
    print(f"{'='*60}")
    print(f"✅ 通過: {len(results['passed'])} 場 — {results['passed']}")
    if results["failed"]:
        print(f"❌ 失敗: {len(results['failed'])} 場 — {results['failed']}")

    # ── SGM + Banker Report ──
    sgm_ok = False
    if results["passed"] and os.path.exists(GENERATE_SGM):
        print(f"\n📋 生成 Master SGM + Banker 報告...")
        sgm_ok = validate_reports_for_release(target_dir, results["passed"]) and run_script(
            GENERATE_SGM,
            ["--dir", target_dir, "--games", *results["passed"]],
            label="SGM Master Report",
        )

    # ── State persistence ──
    write_state(
        target_dir,
        [g["tag"] for g in games],
        "pipeline_partial"
        if results["failed"] or not sgm_ok
        else "pipeline_complete",
    )

    # ── Status ──
    print_status(target_dir, [g["tag"] for g in games])

    if results["failed"]:
        print(f"\n⚠️ {len(results['failed'])} 場失敗。修復後可重跑。")
    release_action = _release_action(passed=bool(results["passed"]), failed=bool(results["failed"]), sgm_ok=sgm_ok)
    if release_action == "blocked":
        print(
            "\n⛔ NBA 分析未完整通過，Cloudflare Dashboard 唔會更新。"
            "請先修復失敗場次再重跑。"
        )
    else:
        print(f"\n🎉 Pipeline 完全完成！無需進一步操作。")
        run_post_success_cloudflare_deploy(
            source="NBA Wong Choi",
            target_dir=target_dir,
            skip=args.skip_cloudflare_deploy,
        )

    completion = "未完成" if release_action == "blocked" else "完成"
    print(f"\n🎯 [Orchestrator] Pipeline {completion}！")
    print(f"所有報告位於: {target_dir}")
    if release_action == "blocked":
        waiting_only = bool(results["waiting"]) and set(results["waiting"]) == set(results["failed"])
        if waiting_only:
            print("NBA_PIPELINE_RESULT: " + json.dumps({
                "status": "waiting_player_markets",
                "reason": "player_markets_not_open",
                "waiting_games": sorted(results["waiting"]),
            }, ensure_ascii=False))
        else:
            # Machine-readable outcome so the scheduler can freeze the games
            # that did pass instead of losing the whole day's prediction.
            print("NBA_PIPELINE_RESULT: " + json.dumps({
                "status": "games_blocked",
                "reason": "per_game_firewall_or_pipeline_failure",
                "passed_games": sorted(results["passed"]),
                "blocked_games": sorted(results["failed"]),
                "waiting_games": sorted(results["waiting"]),
                "sgm_ok": bool(sgm_ok),
            }, ensure_ascii=False))
        sys.exit(75 if waiting_only else 1)
    sys.exit(0)


if __name__ == "__main__":
    main()
