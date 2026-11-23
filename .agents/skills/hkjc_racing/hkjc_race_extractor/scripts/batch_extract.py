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

    `fresh_ok` only ever means "this refresh succeeded".  Since 2026-11-22 the
    publish gate also accepts a ``kept`` formguide, but only after
    `_kept_formguide_matches_racecard` checks it runner-by-runner against this
    run's fresh racecard (the only parts of a formguide that change on race day
    are today's draw / jockey / weight, and the racecard has those).  The three-way `state` exists so
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


# 舊賽績檔要同今次 fresh 排位表逐匹對得上嘅欄位。賽績檔每匹馬頭幾行就係今仗嘅
# 馬號／馬名／檔位／騎師／負磅，所以換騎、改磅、抽籤後檔位變都會令佢對唔上。
_FORMGUIDE_MATCH_FIELDS = ('馬名', '檔位', '騎師', '負磅')


def _runner_blocks(text):
    """`{馬號: {欄位: 值}}`，按 `馬號:` 切開；只讀 `_FORMGUIDE_MATCH_FIELDS`。"""
    runners, current = {}, None
    for line in text.splitlines():
        m = re.match(r'^馬號:\s*(\d+)\b', line)
        if m:
            current = runners.setdefault(int(m.group(1)), {})
            continue
        if current is None:
            continue
        key, sep, value = line.partition(':')
        key = key.strip()
        if sep and key in _FORMGUIDE_MATCH_FIELDS and key not in current:
            value = value.strip()
            if key == '騎師':
                # 排位表寫「周俊樂 (-2)」（見習減磅），賽績檔寫「周俊樂」。
                claim = re.search(r'\s*\((-?\d+)\)\s*$', value)
                if claim:
                    current['_claim'] = abs(int(claim.group(1)))
                    value = value[:claim.start()]
            current[key] = value
    return runners


def _scratched_numbers(racecard_text):
    """排位表入面 `馬名: X (退出)` 嘅馬號 —— 賽績檔可能有、可能已經剷走。"""
    return {int(m.group(1)) for m in re.finditer(
        r'^馬號:\s*(\d+)\s*\n馬名:[^\n]*\(退出\)', racecard_text, re.M)}


def _kept_formguide_matches_racecard(rc_path, fg_path, date_raw):
    """舊賽績檔可唔可以頂替今次失敗嘅刷新：``(ok, reason)``。

    2026-11-22 沙田：00:08 已經成功發佈，之後每 ~7 分鐘一個 run 重抽 11 場賽績，
    每次總有一場 HKJC 隨機回 `no runner rows`（00:52 R5 得、01:13 R5 唔得），
    舊閘要 11 場同一次全部 fresh，結果連續 6 次 exit 75，而碟上嘅 R5 賽績檔
    14/14 匹齊、同 fresh 排位表逐匹一樣。賽績係往績，賽日唔會變；會變嘅只係
    賽績檔入面今仗嗰幾欄（檔位／騎師／負磅），而嗰幾欄 fresh 排位表有。所以：
    排位表今次 fresh，而舊賽績檔係同一個賽日、（剔走排位表標「退出」嘅馬之後）
    馬號集合一樣、每匹 `_FORMGUIDE_MATCH_FIELDS` 全部同排位表一樣，先當齊。
    騎師比較前剷走見習減磅「(-2)」；負磅接受讓磅或者扣咗減磅嘅實際負磅。任何一樣對唔上就照舊等。

    2026-11-22 全日 11 場真檔驗證：11/11 對得上（退出馬 R9 3 號、見習減磅都要
    先處理，唔處理會 9/11 誤判對唔上）。
    """
    try:
        with open(rc_path, 'r', encoding='utf-8') as handle:
            rc_text = handle.read()
        with open(fg_path, 'r', encoding='utf-8') as handle:
            fg_text = handle.read()
    except OSError as exc:
        return False, f"讀唔到檔：{exc}"
    y, mth, d = date_raw.split('/')
    if f"{d}/{mth}/{y}" not in fg_text.split('#### 全場馬匹分析')[0]:
        return False, "賽績檔賽事日期唔係今個賽日"
    scratched = _scratched_numbers(rc_text)
    rc = {n: v for n, v in _runner_blocks(rc_text).items() if n not in scratched}
    fg = {n: v for n, v in _runner_blocks(fg_text).items() if n not in scratched}
    if not rc:
        return False, "排位表冇馬匹"
    if set(rc) != set(fg):
        return False, f"馬號唔同：排位表 {sorted(rc)} vs 賽績 {sorted(fg)}"
    for num in sorted(rc):
        for key in _FORMGUIDE_MATCH_FIELDS:
            want, got = rc[num].get(key), fg[num].get(key)
            if key == '負磅' and want and want.isdigit() and rc[num].get('_claim'):
                # 排位表係讓磅（133），賽績檔係扣咗見習減磅嘅實際負磅（131）；兩個都接受。
                if got in (want, str(int(want) - rc[num]['_claim'])):
                    continue
            if want is None or want != got:
                return False, (f"{num}號 {key} 唔同：排位表 {rc[num].get(key)!r}"
                               f" vs 賽績 {fg[num].get(key)!r}")
    return True, ""



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
    `_keep_valid_candidate`.  Since 2026-11-03 `starter_pdf_ready` is **not**
    part of the publish gate any more (see `main`): a missing PDF is recorded
    as a warning and the overseas form falls back to the per-horse fsc PDFs.

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
            # Each race fetches every runner serially. A fixed five-minute
            # meeting budget cut off R11 on 2026-10-19 after R1-R10 finished.
            capture_output=True, text=True, timeout=max(300, 60 * len(races)),
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
        print(f"   ⚠️ Starter PDF failed ({pdf_state}): {pdf_err}")
        print(f"   ↪ PDF 唔再卡發佈閘：海外往績會逐匹改用 fsc 來港前賽績（只係警告）。")
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

    # 刷新失敗但舊賽績檔仲喺度：對返今次 fresh 排位表，對得上就當齊（見
    # `_kept_formguide_matches_racecard`）。`formguide_ok` 照舊只代表「今次刷新成功」。
    for result in all_results:
        result['formguide_usable'] = bool(result.get('formguide_ok'))
        if (not result.get('formguide_ok') and result.get('racecard_ok')
                and result.get('formguide_state') == 'kept'):
            r = result['race']
            ok, why = _kept_formguide_matches_racecard(
                os.path.join(output_dir, f"{date_prefix} Race {r} 排位表.md"),
                os.path.join(output_dir, f"{date_prefix} Race {r} 賽績.md"),
                date_raw,
            )
            result['formguide_usable'] = ok
            if ok:
                print(f"   ♻️ Race {r}: 賽績刷新失敗，舊檔同今次排位表逐匹對得上 —— 當齊")
            else:
                result['errors'].append(f"Formguide R{r}: 舊檔對唔上排位表（{why}）")
                print(f"   ❌ Race {r}: 舊賽績檔對唔上排位表 —— {why}")

    # Step 3b: 晨操 (trackwork) —— 一定要喺排位表之後抽（2026-11-23 修）：
    # extract_trackwork 用本地排位表做馬匹名單（parse_racecard_horse_list），
    # 冇排位表就跌返去 HKJC localtrackwork 頁 —— 嗰頁唔跟後備馬補上更新。
    # 11-25 跑馬地 R2：晨操先抽 → 用咗舊名單（雙子美麗、皇金合），補上嘅天下寵兒、領袖勁力冇晨操、冇「練馬師親自操」標籤。
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
        # PDF 唔再阻塞，但一定要印出嚟 —— 靜靜 fallback 等於冇人知。
        print(f"   ⚠️ Starter PDF: {pdf_state} —— {pdf_err or '冇記錄原因'}"
              f"（唔阻塞；海外往績改用 fsc 後備）")
    if tw_results['ok']:
        print(f"   ✅ 晨操 Trackwork: {tw_ok_count}/{len(races)} races")
    else:
        print(f"   ⚠️ 晨操 Trackwork: {tw_ok_count}/{len(races)} races (fallback)")
    print(f"   📁 All files saved to: {output_dir}")

    # 發佈閘：排位表要今次刷新成功（fresh）；賽績 fresh，或者舊檔逐匹對得上
    # 今次 fresh 排位表（2026-11-22 起）。
    #
    # starter PDF 2026-11-03 起由硬條件降做**警告**。佢喺評分入面嘅唯一用途係
    # 自購馬嘅海外往績，而每匹自購馬另有一份靜態嘅 fsc「來港前賽績記錄」PDF，
    # `inject_hkjc_fact_anchors` 喺 PDF 冇海外節時會逐匹改用佢（同一個 row shape、
    # 1,426 匹次對照 1,410 完全一致，見 docs/audits/hkjc-starter-pdf-soft-gate-20261103.md）。
    # 以前 PDF 一斷就卡死成個場次：2026-09-06 沙田 22 次 run 有 20 次卡喺 PDF。
    #
    # PDF 仍然係主來源：佢喺度就用佢，排名唔郁；佢唔喺度就喺 readiness、digest
    # 同 Data_Health 出警告（`starter_pdf_soft_fail`）。
    #
    # `WC_HKJC_GATE` 照樣讀同記錄（scheduler 會傳 `field_change`）。以前佢只係鬆
    # PDF 嗰一格；PDF 唔再入閘之後，兩個模式嘅 `ready` 條式一樣 —— 排位表照樣
    # 要 fresh，退出馬照樣會被攞走。
    gate_mode = os.environ.get("WC_HKJC_GATE", "strict").strip().lower()
    if gate_mode not in ("strict", "field_change"):
        print(f"   ⚠️ 唔認得嘅 WC_HKJC_GATE={gate_mode!r}，當 strict 處理")
        gate_mode = "strict"
    pdf_valid = pdf_state in ("fresh", "kept")
    # 排位表一定要今次 fresh（退出馬、換騎靠佢）；賽績 fresh，或者舊檔經
    # `_kept_formguide_matches_racecard` 對得上（Kelvin 2026-11-22）。
    usable_fg = sum(1 for r in all_results if r.get('formguide_usable'))
    kept_verified = [r['race'] for r in all_results
                     if r.get('formguide_usable') and not r.get('formguide_ok')]
    ready = total_rc == len(races) and usable_fg == len(races)
    starter_pdf_soft_fail = not pdf_ok
    if starter_pdf_soft_fail:
        how = "用碟上舊有效檔" if pdf_valid else "海外往績改用 fsc 後備"
        print(f"   ⚠️ starter PDF 今次未刷新成功（{pdf_state}）—— 唔阻塞發佈，{how}。")
    readiness = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec='seconds'),
        "status": "ready" if ready else "waiting_source",
        "meeting_date": date_raw,
        "expected_races": len(races),
        "starter_pdf_ready": pdf_ok,
        # 2026-11-03 起 `starter_pdf_ready` 唔再入 `ready`；失敗只係
        # `starter_pdf_soft_fail` 警告（digest／Data_Health 會講）。原因同狀態照記，
        # 因為 2026-09-06 個教訓係：冇記低原因，通知就會指錯地方。
        "starter_pdf_gate": "soft",
        "starter_pdf_soft_fail": starter_pdf_soft_fail,
        "starter_pdf_state": pdf_state,
        "gate_mode": gate_mode,
        "starter_pdf_error": pdf_err or "",
        "trackwork_error": tw_results.get('error', ''),
        "racecards_ready": total_rc,
        "formguides_ready": total_fg,
        "racecards_valid": valid_rc,
        "formguides_valid": valid_fg,
        # 已經計入 `ready`：fresh + 舊檔對得上排位表。
        "formguides_usable": usable_fg,
        "formguides_kept_verified": kept_verified,
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
