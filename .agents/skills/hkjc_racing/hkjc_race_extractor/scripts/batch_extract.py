#!/usr/bin/env python3
import glob
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
Batch extraction script for HKJC race data.
Extracts racecard + formguide + trackwork (晨操) for multiple races concurrently,
plus the starter PDF (once per meeting).

Usage:
    python batch_extract.py --base_url "https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/03/04&Racecourse=HV&RaceNo=1" --races 1-9 --output_dir "/path/to/output"

Arguments:
    --base_url: Any racecard URL from the meeting (used to derive date and racecourse)
    --races: Race range (e.g., "1-9" or "1,3,5" or "1")
    --output_dir: Target folder for output files
"""
import re
import argparse
import json
import tempfile
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs

# Paths to existing extraction scripts
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
# Cross-platform venv detection
import platform as _platform
_venv_base = os.path.join(SKILL_DIR, '..', 'venv')
if _platform.system() == 'Windows':
    _venv_win = os.path.join(_venv_base, 'Scripts', 'python.exe')
    VENV_PYTHON = _venv_win if os.path.isfile(_venv_win) else sys.executable
else:
    _venv_unix = os.path.join(_venv_base, 'bin', 'python')
    VENV_PYTHON = _venv_unix if os.path.isfile(_venv_unix) else sys.executable
RACECARD_SCRIPT = os.path.join(SKILL_DIR, 'extract_racecard.py')
FORMGUIDE_SCRIPT = os.path.join(SKILL_DIR, 'extract_formguide_playwright.py')
STARTER_PDF_SCRIPT = os.path.join(SKILL_DIR, 'extract_starter_pdf.py')
TRACKWORK_SCRIPT = os.path.join(SKILL_DIR, 'extract_trackwork.py')

# Force UTF-8 for child subprocess output (prevents garbled Chinese on non-macOS systems)
SUBPROCESS_ENV = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
EXIT_TEMPORARY = 75


def _atomic_write_text(path, content):
    """Replace an extracted artifact only after a complete candidate exists."""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=os.path.dirname(path),
            prefix=f'.{os.path.basename(path)}.', suffix='.tmp', delete=False,
        ) as handle:
            handle.write(content)
            temp_path = handle.name
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def _atomic_write_json(path, payload):
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + '\n')


def _content_error(content, label, race_no):
    encoded_size = len(content.encode('utf-8'))
    if "Could not find racecard table" in content or "沒有賽績紀錄" in content:
        return f"{label} R{race_no}: source not published/ready"
    if encoded_size < 100:
        return f"{label} R{race_no}: Output suspiciously small ({encoded_size} bytes)"
    first_line = content.strip().split('\n')[0] if content.strip() else ''
    if first_line.startswith('Error:'):
        return f"{label} R{race_no}: {first_line[:100]}"
    if label in {'Racecard', 'Formguide'} and not re.search(r'^馬號:\s*\d+\b', content, re.M):
        return f"{label} R{race_no}: no runner rows (source not published/ready)"
    return None


def _artifact_state(path, label, race_no):
    """`kept` when the file already on disk is usable, else `missing`.

    Used on the paths where the refresh never produced content at all (the
    extractor timed out or could not be launched).  Those paths must still be
    able to say "we already have good data" — otherwise a transient failure
    reads exactly like having nothing.
    """
    if not os.path.exists(path):
        return 'missing'
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return 'missing' if _content_error(handle.read(), label, race_no) else 'kept'
    except OSError:
        return 'missing'


def _keep_valid_candidate(path, content, label, race_no, returncode):
    """Validate before replace; failed refreshes never destroy last good data.

    Returns ``(fresh_ok, error, state)`` where ``state`` is what the artifact
    actually is after this run:

      ``fresh``    this run scraped valid content and wrote it
      ``kept``     this run failed, but the file already on disk is still valid
      ``missing``  there is no valid data for this race at all

    `fresh_ok` (the publish gate) stays as strict as before: only ``fresh``
    counts, because a formguide can change up to race day and analysing a
    stale one silently is worse than waiting.  The three-way `state` exists so
    the **alert** can stop conflating ``kept`` with ``missing`` — 2026-09-05
    the 09-06 ShaTin notice read "未齊：R1賽績、R2賽績、R3賽績" when all three
    files were on disk and complete (14.5 / 12.7 / 12.5 formline rows per
    runner, the richest on the card); HKJC had merely returned no runner rows
    for that one refresh.  Same shape on 09-04 (8/10).  A reader cannot act on
    an alert that says the same thing whether the data is there or gone.
    """
    error = _content_error(content, label, race_no)
    if returncode == 0 and error is None:
        _atomic_write_text(path, content)
        return True, None, 'fresh'
    if returncode != 0 and error is None:
        error = f"{label} R{race_no}: extractor exit={returncode}"
    state = 'missing'
    # Remove only an already-invalid artifact left by an older non-atomic run.
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                existing_error = _content_error(handle.read(), label, race_no)
            if existing_error:
                os.unlink(path)
            else:
                state = 'kept'
        except OSError:
            pass
    return False, error, state



def parse_races(race_str):
    """Parse race specification like '1-9' or '1,3,5' or '1'"""
    races = []
    for part in race_str.split(','):
        part = part.strip()
        if '-' in part:
            start, end = part.split('-')
            races.extend(range(int(start), int(end) + 1))
        else:
            races.append(int(part))
    return sorted(set(races))


def derive_urls(base_url, race_no):
    """Derive racecard and formguide URLs for a given race number."""
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query)
    date = qs.get('racedate', [''])[0]
    course = qs.get('Racecourse', [''])[0]

    racecard_url = f"https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date}&Racecourse={course}&RaceNo={race_no}"
    formguide_url = f"https://racing.hkjc.com/zh-hk/local/info/speedpro/formguide?racedate={date}&Racecourse={course}&RaceNo={race_no}"
    return racecard_url, formguide_url


def extract_single_race(race_no, base_url, output_dir, date_prefix):
    """Extract racecard + formguide for a single race."""
    racecard_url, formguide_url = derive_urls(base_url, race_no)
    results = {'race': race_no, 'racecard_ok': False, 'formguide_ok': False,
               'racecard_state': 'missing', 'formguide_state': 'missing', 'errors': []}

    # Racecard
    rc_file = os.path.join(output_dir, f"{date_prefix} Race {race_no} 排位表.md")
    try:
        rc_result = subprocess.run(
            [VENV_PYTHON, RACECARD_SCRIPT, racecard_url],
            capture_output=True, text=True, timeout=60,
            encoding='utf-8', env=SUBPROCESS_ENV
        )
        ok, error, state = _keep_valid_candidate(
            rc_file, rc_result.stdout or '', 'Racecard', race_no, rc_result.returncode
        )
        results['racecard_ok'] = ok
        results['racecard_state'] = state
        if not ok:
            results['errors'].append(error or f"Racecard R{race_no}: {rc_result.stderr[:200]}")
    except Exception as e:
        results['errors'].append(f"Racecard R{race_no}: {str(e)}")

    # Formguide
    fg_file = os.path.join(output_dir, f"{date_prefix} Race {race_no} 賽績.md")
    try:
        fg_result = subprocess.run(
            [VENV_PYTHON, FORMGUIDE_SCRIPT, formguide_url],
            capture_output=True, text=True, timeout=120,
            encoding='utf-8', env=SUBPROCESS_ENV
        )
        # Filter out the "Extracting form guide" log line
        lines = fg_result.stdout.splitlines(keepends=True)
        filtered = [l for l in lines if "Extracting form guide using Playwright" not in l]
        content = ''.join(filtered)
        ok, error, state = _keep_valid_candidate(
            fg_file, content, 'Formguide', race_no, fg_result.returncode
        )
        results['formguide_ok'] = ok
        results['formguide_state'] = state
        if not ok:
            results['errors'].append(error or f"Formguide R{race_no}: {fg_result.stderr[:200]}")
    except Exception as e:
        results['errors'].append(f"Formguide R{race_no}: {str(e)}")

    return results


def extract_starter_pdf(date_yyyymmdd, output_dir, date_prefix):
    """Extract the starter PDF (once per meeting).

    Returns ``(fresh_ok, error, state)`` — same three-way contract as
    `_keep_valid_candidate`, because `starter_pdf_ready` is a **hard** term in
    the publish gate (`ready = pdf_ok and racecards and formguides`), so a
    transient PDF failure blocks the whole meeting on its own.

    ⚠️ 2026-09-05: this function used to unpack two values here while
    `_keep_valid_candidate` had been changed to return three.  The `ValueError`
    was swallowed by a bare `except Exception` and reported as a *source*
    failure, so the starter PDF failed **20 of 22 runs** for 2026-09-06 ShaTin
    — 0/22 passed the gate — while the extractor itself took 11.2s and exited
    0.  Nothing in the log or the readiness JSON named the reason.  That is why
    the exception handling below is narrow and why the error is now recorded.
    """
    pdf_file = os.path.join(output_dir, f"{date_prefix} 全日出賽馬匹資料 (PDF).md")
    try:
        result = subprocess.run(
            [VENV_PYTHON, STARTER_PDF_SCRIPT, date_yyyymmdd],
            capture_output=True, text=True, timeout=90,
            encoding='utf-8', env=SUBPROCESS_ENV
        )
    except (subprocess.SubprocessError, OSError) as exc:
        # Only *running* the extractor is allowed to fail softly here.  A bug in
        # our own code must not be laundered into "HKJC is not ready".
        return False, f"Starter PDF: {type(exc).__name__}: {exc}", _artifact_state(
            pdf_file, 'Starter PDF', 0)
    ok, error, state = _keep_valid_candidate(
        pdf_file, result.stdout or '', 'Starter PDF', 0, result.returncode
    )
    return ok, "" if ok else (error or result.stderr[:200]), state


def _trackwork_file_ok(output_dir, race_no, suffix, min_bytes):
    """True when a non-trivial 晨操 file for this race exists, whatever its
    date prefix. Returns the largest match so a stale empty file next to a
    good one cannot fail the check."""
    pattern = os.path.join(output_dir, f"*Race {race_no} 晨操.{suffix}")
    sizes = [os.path.getsize(p) for p in glob.glob(pattern) if os.path.isfile(p)]
    return bool(sizes) and max(sizes) > min_bytes


def extract_trackwork_meeting(base_url, races, output_dir, date_prefix):
    """Extract 晨操 (morning trackwork) for all races in one call.
    Uses --fail-soft so missing data doesn't abort the pipeline."""
    results = {'ok': False, 'races': {}, 'error': ''}
    race_list = ','.join(str(r) for r in races)
    result = None
    try:
        result = subprocess.run(
            [VENV_PYTHON, TRACKWORK_SCRIPT,
             '--base_url', base_url,
             '--races', race_list,
             '--output_dir', output_dir,
             '--fail-soft'],
            capture_output=True, text=True, timeout=300,
            encoding='utf-8', env=SUBPROCESS_ENV
        )
    except (subprocess.SubprocessError, OSError) as exc:
        results['error'] = f"{type(exc).__name__}: {exc}"
    # ⚠️ 呢個 loop 一定要喺 try **外面**。佢查嘅係碟上實物，唔係 subprocess
    # 點收場 —— 而 `extract_trackwork.py` 係逐場寫檔嘅，所以 300 秒 timeout
    # 殺咗個 subprocess 之後，已經寫好嗰批仍然完整。2026-09-05 呢個 loop
    # 喺 try 入面：一 timeout 就整個跳過，`races` 留空 → 報「晨操 0/10
    # (fallback)」，而 20 個檔（261 KB json / 50 KB md）全部喺碟上。
    # 實測 22 次 run 有 9 次（41%）中招。
    for r in races:
        # ⚠️ Match by suffix, not by `date_prefix`. This module builds
        # `09-06` (MM-DD) while `extract_trackwork.py` writes
        # `2026-09-06` (YYYY-MM-DD), so an exact-path check could never
        # find the files it had just written: every run reported
        # "晨操 0/N (fallback)" and stored `trackwork_ready: 0` while all
        # N races were on disk and complete. Globbing keeps the check
        # working if either side changes its prefix again.
        results['races'][r] = {
            'json_ok': _trackwork_file_ok(output_dir, r, "json", 100),
            'md_ok': _trackwork_file_ok(output_dir, r, "md", 50),
        }
    total_ok = sum(1 for v in results['races'].values() if v['json_ok'] and v['md_ok'])
    results['ok'] = total_ok > 0
    if result is not None and result.returncode != 0 and not results['error']:
        results['error'] = result.stderr[:200]
    return results


def main():
    parser = argparse.ArgumentParser(description="Batch extract HKJC race data")
    parser.add_argument("--base_url", required=True, help="Any racecard URL from the meeting")
    parser.add_argument("--races", required=True, help="Race range: '1-9' or '1,3,5' or '1'")
    parser.add_argument("--output_dir", required=True, help="Target output folder")
    parser.add_argument("--max_workers", type=int, default=3, help="Max concurrent extractions (default: 3)")
    args = parser.parse_args()

    # Parse inputs
    races = parse_races(args.races)
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    # Derive date info from URL — fail-fast on missing/malformed racedate
    parsed = urlparse(args.base_url)
    qs = parse_qs(parsed.query)
    date_raw = qs.get('racedate', [''])[0]  # e.g., "2026/03/04"
    date_parts = date_raw.split('/')
    if len(date_parts) != 3 or not all(date_parts):
        print(f"❌ FATAL: Invalid or missing 'racedate' in URL: '{date_raw}'")
        print(f"   Expected format: YYYY/MM/DD (e.g., 2026/03/25)")
        print(f"   Full URL: {args.base_url}")
        sys.exit(1)
    date_yyyymmdd = ''.join(date_parts)  # "20260304"
    if len(date_yyyymmdd) != 8 or not date_yyyymmdd.isdigit():
        print(f"❌ FATAL: Date failed numeric validation: '{date_yyyymmdd}' (from '{date_raw}')")
        sys.exit(1)
    date_prefix = f"{date_parts[1]}-{date_parts[2]}"

    print(f"🏇 HKJC Batch Extraction")
    print(f"   Races: {races}")
    print(f"   Output: {output_dir}")
    print(f"   Date: {date_raw}")
    print()

    # Step 1: Extract starter PDF (once)
    print(f"📄 Extracting starter PDF...")
    pdf_ok, pdf_err, pdf_state = extract_starter_pdf(date_yyyymmdd, output_dir, date_prefix)
    if pdf_ok:
        print(f"   ✅ Starter PDF saved")
    else:
        print(f"   ❌ Starter PDF failed ({pdf_state}): {pdf_err}")
        print(f"   ⏳ PDF 未 ready；先完成其餘來源探測，整批會標記 WAITING_SOURCE。")
    print()

    # Step 2: Extract 晨操 (trackwork) — all races in one shot, fail-soft
    print(f"🏇 Extracting 晨操 (trackwork) for {len(races)} races...")
    tw_results = extract_trackwork_meeting(args.base_url, races, output_dir, date_prefix)
    tw_ok_count = sum(1 for v in tw_results['races'].values() if v['json_ok'] and v['md_ok'])
    if tw_results['ok']:
        print(f"   ✅ 晨操: {tw_ok_count}/{len(races)} races")
    else:
        print(f"   ⚠️ 晨操: {tw_ok_count}/{len(races)} races (下游將使用 fallback)")
        if tw_results['error']:
            print(f"      {tw_results['error']}")
    print()

    # Step 3: Extract racecard + formguide concurrently
    print(f"🔄 Extracting {len(races)} races (max {args.max_workers} concurrent)...")
    all_results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(extract_single_race, r, args.base_url, output_dir, date_prefix): r
            for r in races
        }
        for future in as_completed(futures):
            result = future.result()
            all_results.append(result)
            race = result['race']
            # ♻️ = 刷新失敗但碟上舊檔仍然有效；❌ = 真係冇有效數據。
            marks = {'fresh': "✅", 'kept': "♻️", 'missing': "❌"}
            rc = marks.get(result.get('racecard_state'), "❌")
            fg = marks.get(result.get('formguide_state'), "❌")
            print(f"   Race {race}: Racecard {rc} | Formguide {fg}")
            for err in result['errors']:
                print(f"      ⚠️ {err}")

    # Summary
    all_results.sort(key=lambda x: x['race'])
    total_rc = sum(1 for r in all_results if r['racecard_ok'])
    total_fg = sum(1 for r in all_results if r['formguide_ok'])
    # `*_ok` counts a successful refresh; `*_valid` counts races that have
    # usable data on disk afterwards (fresh + kept).  Both are needed: the gate
    # wants the first, a human reading the alert wants the second.
    def _valid(key):
        return sum(1 for r in all_results
                   if r.get(f'{key}_state', 'missing') in ('fresh', 'kept'))
    valid_rc, valid_fg = _valid('racecard'), _valid('formguide')
    print()
    print(f"📊 Summary: {total_rc}/{len(races)} racecards | {total_fg}/{len(races)} formguides"
          f" (refreshed)")
    if valid_rc != total_rc or valid_fg != total_fg:
        print(f"   ↳ 碟上有效: {valid_rc}/{len(races)} racecards | {valid_fg}/{len(races)} formguides"
              f" —— 差額係刷新失敗但保留咗上次有效檔，唔係冇數據")
    if pdf_ok:
        print(f"   ✅ Starter PDF: OK")
    else:
        # 冇呢個 else，一個**硬阻塞**條件失敗喺 summary 度係完全睇唔到嘅。
        print(f"   ❌ Starter PDF: {pdf_state} —— {pdf_err or '冇記錄原因'}")
    if tw_results['ok']:
        print(f"   ✅ 晨操 Trackwork: {tw_ok_count}/{len(races)} races")
    else:
        print(f"   ⚠️ 晨操 Trackwork: {tw_ok_count}/{len(races)} races (fallback)")
    print(f"   📁 All files saved to: {output_dir}")

    # 發佈閘。預設（`strict`）要每個來源今次都刷新成功。
    #
    # `WC_HKJC_GATE=field_change` 係為「名單有變，要攞走退出馬」嗰種重跑而設，
    # 只鬆**一格**：starter PDF 由 `fresh` 放寬到 `valid`（fresh 或 kept）。
    # 排位表同賽績照樣要 fresh —— 佢哋決定名單（賽績尤其：Facts 個馬匹迴圈
    # 食嘅就係佢），鬆咗就會由舊檔重建，隻退出馬返晒嚟。
    #
    # 點解 PDF 鬆得：佢係一份**賽前**文件，自己聲明咗截止時間。實測 2026-09-06
    # 沙田嘅 `最終版本` 截止喺 09-05 上午 11:30 —— 即係定義上永遠早過賽事，
    # 冇可能載到賽日嘅退出馬。而 `初版`→`最終版本` 2,347 行入面只有 3 行抬頭
    # 唔同，2,344 行數據逐位元一樣。用一份 `kept` PDF 去做「攞走退出馬」嘅
    # 重跑，資訊上同 `fresh` 冇分別。
    #
    # 支撐嘅唔對稱：板上掛住一隻唔跑嘅馬做首選係主動出錯；用一份今朝嘅 PDF
    # 分析（數據同下午嗰份一樣）係良性。
    gate_mode = os.environ.get("WC_HKJC_GATE", "strict").strip().lower()
    if gate_mode == "field_change":
        pdf_gate = pdf_state in ("fresh", "kept")
    else:
        if gate_mode != "strict":
            print(f"   ⚠️ 唔認得嘅 WC_HKJC_GATE={gate_mode!r}，當 strict 處理")
        pdf_gate = pdf_ok
    ready = pdf_gate and total_rc == len(races) and total_fg == len(races)
    if gate_mode == "field_change" and pdf_gate and not pdf_ok:
        print(f"   ℹ️ 名單變動模式：PDF 用碟上有效檔（{pdf_state}）過閘 —— "
              f"PDF 截止時間必定早過賽事，唔會載到賽日退出馬。")
    readiness = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec='seconds'),
        "status": "ready" if ready else "waiting_source",
        "meeting_date": date_raw,
        "expected_races": len(races),
        "starter_pdf_ready": pdf_ok,
        # `starter_pdf_ready` 係 `ready` 嘅硬條件，所以佢失敗會單獨卡死成個場次。
        # 之前 readiness 完全冇記低原因，`hkjc_daily_schedule.readiness_digest`
        # 亦冇任何一行講 PDF —— 於是 2026-09-06 沙田連續 22 次 run 都過唔到閘，
        # 而通知每次都指住幾場「賽績」，即係指錯地方。
        "starter_pdf_state": pdf_state,
        "gate_mode": gate_mode,
        "starter_pdf_error": pdf_err or "",
        "trackwork_error": tw_results.get('error', ''),
        "racecards_ready": total_rc,
        "formguides_ready": total_fg,
        "racecards_valid": valid_rc,
        "formguides_valid": valid_fg,
        "trackwork_ready": tw_ok_count,
        "races": all_results,
        "self_recovery": "automatic_retry" if not ready else "not_needed",
    }
    readiness_path = os.path.join(output_dir, "Extraction_Readiness.json")
    _atomic_write_json(readiness_path, readiness)
    print(f"   Readiness: {readiness['status']} ({readiness_path})")
    if not ready:
        print("⏳ HKJC required source 未齊；保留最後有效檔案，exit 75 等 scheduler 自動重試。")
        sys.exit(EXIT_TEMPORARY)


if __name__ == "__main__":
    main()
