#!/usr/bin/env python3
"""獨立核實：今日賽事分析咗未？上咗 dashboard 未？唔得就補、補唔到就嗌。

⚠️ **要獨立過個排程 process 先有意義。** 現有嘅補救（補發、補覆盤、補抽）全部住喺
排程自己入面 —— 個 run 早死、crash、或者根本冇開（部機瞓咗、launchd 出事、鎖俾
人霸住），就冇任何嘢會發現。2026-08-05 至 08-10 三次多日空白，每次都係「有嘢
失敗咗，而冇人去問今日到底出咗未」。

判斷一律睇**實物**，唔睇 log：live JSON 有冇今日場次，本機有冇評分檔。一個報
「成功」嘅 run log 已經呃過我哋兩次。

自愈只做一件事：**由本機已評分嘅場次重建再發佈**（唔出網、成本低、唔會同人爭）。
「分析根本冇做」修唔到 —— 嗰個要抽幾百版，唔應該由一個 healthcheck 靜靜咁觸發，
所以出通知畀人決定。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))

LIVE_URL = "https://wongchoi-dashboard.pages.dev/dashboard-data.json"
RUNNER = HERE / "run_au_daily_schedule.sh"
JT_COVERAGE_MIN = float(os.environ.get("WC_AU_HEALTH_JT_MIN", "0.80"))
MORNING_ODDS_READY_HOUR = int(os.environ.get("WC_AU_MORNING_ODDS_READY_HOUR", "11"))



def live_meetings() -> set[str] | None:
    """⚠️ 一定要繞開 CDN cache，否則會攞到舊副本而誤判成「冇發佈」。"""
    url = f"{LIVE_URL}?cb={int(datetime.now().timestamp() * 1000)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "WongChoi-Healthcheck/1.0",
        "Cache-Control": "no-cache, max-age=0", "Pragma": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None
    return {f"{m.get('date')}|{m.get('venue')}" for m in d.get("meetings") or []}


def au_venues_today(day: str) -> set[str] | None:
    """今日應該有邊幾個澳洲馬場（Sportsbet API，curl 得到，唔使瀏覽器）。"""
    try:
        import au_daily_schedule as S

        class _Quiet:
            def warn(self, *a, **k): pass
            def step(self, *a, **k): pass
            def retry(self, *a, **k): pass
            data: dict = {}

        events = S.api_next_events(_Quiet())
        by_day = S.events_by_day(events)
        return set(by_day.get(day) or [])
    except Exception:  # noqa: BLE001
        return None


def local_scored(day: str) -> dict[str, int]:
    """{venue: 已評分場數}，本機（未歸檔）嗰批。"""
    from wongchoi_paths import AU_RACING

    out = {}
    for d in Path(AU_RACING).glob(f"{day} *"):
        if not d.is_dir():
            continue
        venue = re.sub(r"\s+Race\s+[\d\-]+$", "", d.name[11:]).strip()
        out[venue] = len(list(d.glob("Race_*_Auto_Analysis.md")))
    return out


def _has_nonempty(paths) -> bool:
    return any(path.exists() and path.is_file() and path.stat().st_size > 0
               for path in paths)


def _require_morning_odds(day: str, now: datetime | None = None) -> bool:
    """09:15 checks run before the 10:00 refresh; 11:00 checks must enforce it."""
    now = now or datetime.now().astimezone()
    today = now.date().isoformat()
    return day < today or (day == today and now.hour >= MORNING_ODDS_READY_HOUR)


def local_quality_issues(day: str, *, root: Path | None = None,
                         require_morning: bool | None = None) -> list[str]:
    """Verify real per-race artifacts, provenance and time-appropriate odds freshness."""
    if root is None:
        from wongchoi_paths import AU_RACING
        root = Path(AU_RACING)
    if require_morning is None:
        require_morning = _require_morning_odds(day)

    issues: list[str] = []
    for folder in sorted(root.glob(f"{day} *")):
        if not folder.is_dir():
            continue
        match = re.search(r"\sRace\s+1-(\d+)$", folder.name)
        if not match:
            issues.append(f"{folder.name}：folder 名解析唔到預期場數")
            continue
        expected = int(match.group(1))
        odds_path = folder / "odds_history.json"
        try:
            odds = json.loads(odds_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            odds = {}

        missing_artifacts: list[str] = []
        stale_odds: list[int] = []
        missing_going_audit: list[int] = []
        unavailable_official_going: list[int] = []
        for race in range(1, expected + 1):
            required = {
                "Racecard": folder.glob(f"* Race {race} Racecard.md"),
                "Formguide": folder.glob(f"* Race {race} Formguide.md"),
                "Facts": folder.glob(f"* Race {race} Facts.md"),
                "Logic": [folder / f"Race_{race}_Logic.json"],
                "Analysis": [folder / f"Race_{race}_Auto_Analysis.md"],
                "Scoring": [folder / f"Race_{race}_Auto_Scoring.csv"],
            }
            for label, paths in required.items():
                if not _has_nonempty(paths):
                    missing_artifacts.append(f"R{race} {label}")

            if require_morning:
                snapshots = (odds.get(str(race)) or {}) if isinstance(odds, dict) else {}
                if not any("morning" in key.partition("|")[2].lower()
                           for key in snapshots):
                    stale_odds.append(race)

            logic = folder / f"Race_{race}_Logic.json"
            try:
                payload = json.loads(logic.read_text(encoding="utf-8"))
                race_analysis = payload.get("race_analysis") or {}
                refresh = race_analysis.get("going_refresh")
                stored_going = str(race_analysis.get("going") or "").strip()
            except (OSError, ValueError, AttributeError):
                refresh = None
                stored_going = ""
            if logic.exists() and not refresh:
                if stored_going and stored_going.lower() != "unknown":
                    missing_going_audit.append(race)
                else:
                    unavailable_official_going.append(race)

        if missing_artifacts:
            issues.append(f"{folder.name}：輸出唔齊（{', '.join(missing_artifacts[:8])}"
                          + ("…" if len(missing_artifacts) > 8 else "") + "）")
        if stale_odds:
            issues.append(f"{folder.name}：11:00 後仍冇 morning odds "
                          f"R{','.join(map(str, stale_odds))}")
        if missing_going_audit:
            issues.append(f"{folder.name}：going_refresh audit 缺 "
                          f"R{','.join(map(str, missing_going_audit))}")
        if unavailable_official_going:
            issues.append(f"{folder.name}：官方 going 未有資料 "
                          f"R{','.join(map(str, unavailable_official_going))}")

        summary = folder / "Meeting_Summary.md"
        try:
            text = summary.read_text(encoding="utf-8")
        except OSError:
            text = ""
        coverage = re.search(
            r"Jockey/trainer LY tokens filled:\s*(\d+);\s*missing:\s*(\d+)", text)
        if coverage:
            filled, missing = map(int, coverage.groups())
            total = filled + missing
            ratio = filled / total if total else 0.0
            if ratio < JT_COVERAGE_MIN:
                issues.append(f"{folder.name}：騎練資料覆蓋 {ratio:.1%} "
                              f"低過門檻 {JT_COVERAGE_MIN:.0%}")
    return issues


def latest_step_issue(step_name: str, *, log_dir: Path | None = None) -> str | None:
    """Read the latest completed occurrence of a critical pipeline step."""
    log_dir = log_dir or (HERE / "logs")
    files = sorted(log_dir.glob("run-*.json"),
                   key=lambda path: path.stat().st_mtime, reverse=True)[:20]
    for path in files:
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for step in reversed(run.get("steps") or []):
            if step.get("step") != step_name or step.get("status") == "start":
                continue
            if step.get("status") not in ("ok", "deploy-skipped-no-change"):
                detail = step.get("detail") or step.get("first_error") or step.get("status")
                return f"{step_name} 最近狀態係 {step.get('status')}：{detail}"
            return None
    return f"搵唔到最近 {step_name} 完成記錄"


def latest_step(step_name: str, *, log_dir: Path | None = None) -> dict | None:
    """最近一次跑完（唔係 `start`）嘅 step 記錄。"""
    log_dir = log_dir or (HERE / "logs")
    files = sorted(log_dir.glob("run-*.json"),
                   key=lambda path: path.stat().st_mtime, reverse=True)[:20]
    for path in files:
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for step in reversed(run.get("steps") or []):
            if step.get("step") == step_name and step.get("status") != "start":
                return step
    return None


def _mirror_stat(path: Path):
    """Return stat, ``None`` for absent, or sentinel for inaccessible.

    Missing and TCC-denied are not the same fact.  Treating both as ``None``
    made a current `.latest` fallback look absent whenever File Provider denied
    stat, so healthcheck kept reporting a stale mirror after a successful run.
    """
    try:
        return path.stat()
    except FileNotFoundError:
        return None
    except OSError:
        return _MIRROR_STAT_UNKNOWN


_MIRROR_STAT_UNKNOWN = object()


def mirror_behind(day: str, *, root: Path | None = None,
                  mirror: Path | None = None) -> list[str] | None:
    """Drive 鏡像實物落後咗邊幾個檔。`None` = 睇唔到鏡像，答唔到。

    **睇實物，唔睇 log** —— 呢個係本檔開頭嗰條紀律，而鏡像檢查之前偏偏犯咗：
    佢報最近一個 mirror step 嘅狀態，所以一個朝早失敗、下午已經修好嘅 run，
    會一路嗌到下一個 run 覆蓋咗個 log 為止。2026-08-21 就係咁：10:27 嗰 run
    因為 TCC 冇授權而 `copied:0`，Kelvin 15:02 授咗 Full Disk Access，鏡像
    其實已經追返 —— 但體檢繼續照嗌同一句。
    """
    if mirror is None:
        from wongchoi_paths import AU_RACING_MIRROR
        if AU_RACING_MIRROR is None:
            return []
        mirror = Path(AU_RACING_MIRROR)
    if root is None:
        from wongchoi_paths import AU_RACING
        root = Path(AU_RACING)

    mirror_stat = _mirror_stat(mirror)
    if mirror_stat is None or mirror_stat is _MIRROR_STAT_UNKNOWN:
        return None

    # 鏡像名單只有一份真源，喺排程模組 —— 抄一份落嚟就一定有一日走樣。
    from au_daily_schedule import MIRRORED_ROOT_FILES

    sources: list[Path] = [root / name for name in MIRRORED_ROOT_FILES]
    for folder in sorted(root.glob(f"{day} *")):
        if folder.is_dir():
            sources.extend(sorted(folder.rglob("*")))

    behind: list[str] = []
    destination_unknown = False
    for src in sources:
        src_st = _mirror_stat(src)
        if (
            src_st is None
            or src_st is _MIRROR_STAT_UNKNOWN
            or not src.is_file()
            or src.name == ".DS_Store"
        ):
            continue
        rel = src.relative_to(root)
        canonical = mirror / rel
        # 個別檔寫唔入會退去 `.latest` 兄弟檔（睇 au_daily_schedule.atomic_copy2），
        # consumers 由 wongchoi_paths 取最新嗰份 —— 所以兩個名有一個夠新就算追到。
        latest = canonical.with_name(f"{canonical.stem}.latest{canonical.suffix}")
        destination_stats = (_mirror_stat(canonical), _mirror_stat(latest))
        if any(st is _MIRROR_STAT_UNKNOWN for st in destination_stats):
            destination_unknown = True
        if any(st is not None and st is not _MIRROR_STAT_UNKNOWN
               and st.st_size == src_st.st_size
               and int(st.st_mtime) >= int(src_st.st_mtime)
               for st in destination_stats):
            continue
        if any(st is _MIRROR_STAT_UNKNOWN for st in destination_stats):
            # We cannot prove absence or staleness. The latest run log remains
            # the fallback source of truth for this best-effort mirror.
            continue
        behind.append(str(rel))
    if behind:
        return behind
    return None if destination_unknown else []


def mirror_issue(day: str | None = None, *, log_dir: Path | None = None) -> str | None:
    """Drive 鏡像值唔值得嗌人。

    鏡像係 best-effort：本機係正本，Cloudflare 由本機發，所以鏡像斷咗**唔影響
    預測同發佈**，只係 Kelvin 同 Windows 機喺 Drive 邊會睇到舊版本。

    先問實物（`mirror_behind`）。睇唔到鏡像嗰陣才退去睇 log，而 log 只有「成步
    完全冇做到嘢」才算 —— 個別檔退去 `.latest` fallback 係設計之內，「263 個
    入咗、1 個用 fallback」報上去只係製造雜訊，而雜訊嘅代價就係下次真出事嗰下
    冇人再睇。
    """
    if day is not None:
        behind = mirror_behind(day)
        if behind is not None:
            if not behind:
                return None
            sample = "、".join(behind[:3]) + ("…" if len(behind) > 3 else "")
            return f"Drive 鏡像落後 {len(behind)} 個檔（{sample}）"

    step = latest_step("mirror", log_dir=log_dir)
    if step is None:
        return "搵唔到最近 mirror 完成記錄"
    status = step.get("status")
    if status in ("ok", "not-configured"):
        return None
    copied, failed = step.get("copied") or 0, step.get("failed") or 0
    if copied and not step.get("gave_up"):
        return None  # 大部分入咗，個別檔退咗去 fallback —— best-effort 做到嘢。
    detail = step.get("first_error") or step.get("reason") or status
    return f"Drive 鏡像今次冇更新到任何檔（{status}，失敗 {failed} 個）：{detail}"


def quality_issues(day: str) -> tuple[list[str], list[str]]:
    """`(阻塞, best-effort)`。

    ⚠️ 兩者一定要分開。之前係同一個 list，所以一個 Drive 鏡像落後會出一句
    「資料品質未過」—— 個訊息本身就係錯嘅：本機係正本、Cloudflare 由本機發，
    鏡像落後影響唔到預測同發佈。報得比實際嚴重同報得比實際輕微一樣壞，因為兩樣
    都會令人開始唔信呢條通知。
    """
    blocking = local_quality_issues(day)
    issue = latest_step_issue("ingest-results")
    if issue:
        blocking.append(issue)

    advisories: list[str] = []
    issue = mirror_issue(day)
    if issue:
        advisories.append(issue)
    return blocking, advisories


def heal() -> tuple[bool, str]:
    """由本機重建再發佈。唔出網抽頁，所以安全、快、唔會同排程爭資源。

    ⚠️ `--slot` 唔可以慳。control plane 見到 `--mode morning` 就會將個 run 釘落
    canonical slot `10:00`（`control_plane.FIXED_MODE_SLOTS`），**唔理實際幾點跑**。
    2026-08-27 至 08-29 三日實測：02:30 體檢叫嘅 `heal()` 攞咗
    `wc:au:run:<date>:morning:10:00` 呢條 idempotency key，於是同一次體檢跟住開
    嘅真補跑、同埋之後 10:00 嗰程 launchd 早更，兩個都變 `duplicate_skipped` ——
    即係當日唯一會補抽場次嘅兩條路都俾一次「重新發佈」封死咗。個補跑仲會 log
    「已自動開始一次補跑」，所以連通知都係報喜。

    每次體檢有自己嘅 slot（`heal-HH:MM`）：一日三次體檢各自有 manifest，互相唔
    撞，亦永遠唔會食到排程嗰兩格。
    """
    slot = f"heal-{datetime.now().strftime('%H:%M')}"
    try:
        r = subprocess.run([str(RUNNER), "morning", "--slot", slot, "--skip-refresh"],
                           capture_output=True, text=True, timeout=3600)
        return r.returncode in (0, 75), (r.stdout or "")[-400:]
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def start_analysis_recovery(day: str) -> tuple[bool, str]:
    """今日完全冇分析時，受控地補開一次正常 morning pipeline。

    呢個唔係「見錯就亂 retry」：caller 已經用 live dashboard、Sportsbet 今日場次
    同本機評分檔三方確認係 `unanalysed`。同一日只開一次，而且 runner 自己仲有
    共用 flock、cache、circuit breaker、完整驗證同 Telegram 完場通知。
    """
    key = f"auto-analysis-{day}"
    if key in _attempted():
        return False, "今日已經自動補跑過一次，唔會無限重試"
    if run_in_progress():
        return False, "而家已有 AU run 跑緊"
    if not RUNNER.exists():
        return False, f"搵唔到 runner：{RUNNER}"

    out = HERE / "logs" / f"auto-recovery-{day}.out"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        _mark(key)  # 開 process 前先記；crash 都唔會變成每次 healthcheck 再開一個。
        with out.open("w") as fh:
            # `--slot recovery`：同上面 `heal()` 一樣，唔可以佔住排程嗰格 10:00。
            # 呢度用一個**固定**名（唔加時間）係有意嘅 —— 補跑一日只應該開一次，
            # 個 manifest 就係 `autofix_attempted.json` 之外嘅第二道防線。
            subprocess.Popen(
                [str(RUNNER), "morning", "--slot", "recovery", "--today", day,
                 "--rounds", "3", "--round-gap", "420"],
                stdout=fh, stderr=fh, start_new_session=True)
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    return True, f"已開始 morning recovery；log：{out.name}"


def run_in_progress() -> bool:
    """而家有冇排程 run 跑緊。

    ⚠️ 冇呢個判斷嘅話，任何排喺個 run 完成之前嘅體檢都**必然**報「冇上線」——
    因為發佈本身就係最後一步 —— 跟住去補發佈，俾把鎖擋住，再send一條假警報。
    假警報係最快令人開始無視通知嘅嘢，而下一次真出事就係嗰個習慣害死你。

    用嗰把共用鎖做判斷，唔數 process：鎖住喺資料根，兩個 checkout 共用，而且
    正正就係「有人喺度郁緊呢批資料」嘅權威訊號。
    """
    import fcntl

    from wongchoi_paths import AU_RACING

    lock = Path(AU_RACING) / ".au_daily_schedule.lock"
    try:
        handle = lock.open("w")
    except OSError:
        return False
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False
    finally:
        handle.close()


ATTEMPTED = HERE / "logs" / "autofix_attempted.json"


def _attempted() -> set[str]:
    try:
        return set(json.loads(ATTEMPTED.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def _mark(name: str) -> None:
    seen = _attempted()
    seen.add(name)
    ATTEMPTED.parent.mkdir(parents=True, exist_ok=True)
    # 只留最近 40 個 —— 夠防重複，又唔會無限膨脹。
    ATTEMPTED.write_text(json.dumps(sorted(seen)[-40:]), encoding="utf-8")


def last_failed_run() -> tuple[Path, dict] | None:
    """最近一個未正常收尾而且未處理過嘅 run。

    `running` 但共用 flock 已經冇人持有 = process crash／被 kill，唔係仲做緊。
    `main()` 開頭已經用 `run_in_progress()` 擋住真正在跑嗰個，所以行到呢度可以
    安全地將最新一個 running log 當成異常。
    """
    files = sorted((HERE / "logs").glob("run-*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:6]
    done = _attempted()
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if d.get("status") in ("failed", "partial", "running") and f.name not in done:
            return f, d
        if d.get("status") == "ok":
            # 之後有成功嘅 run，之前嗰個失敗已經冇意義。
            return None
    return None


def autofix_last_failure() -> str | None:
    """對得上已知模式先修，而且一個 run 只試一次。

    ⚠️ 兩道限制都係刻意：
      * **只修已知模式** —— 一個估出嚟嘅補救可以令情況變差，仲會遮蓋「呢個係新
        問題」呢個最重要嘅訊號。對唔上就淨係報告。
      * **一個 run 只試一次** —— 唔係嘅話，一個修唔到嘅問題會令每次體檢都重跑
        一次發佈，一日三次，而且每次都 send 一條通知。
    """
    import au_diagnose  # noqa: PLC0415

    got = last_failed_run()
    if not got:
        return None
    path, run = got
    if run.get("status") == "running":
        _mark(path.name)
        started = run.get("started_at") or "時間不明"
        return (f"❌ AU 排程冇正常收尾（{path.name}）\n"
                f"開始：{started}\n"
                "run log 仲係 running，但共用鎖已經釋放 —— process 應該中途死亡，"
                "請用 /diag 或 /retry 跟進")
    remedy = au_diagnose.remedy_for(run)
    if not remedy:
        return None
    _mark(path.name)
    if remedy != "republish":
        return f"⚠️ 認得個模式但唔識執行補救「{remedy}」 —— 要人睇"
    ok, detail = heal()
    after = check(date.today().isoformat())
    good = ok and after.get("state") in (
        "ok", "ok-with-advisories", "degraded", "in-progress"
    )
    head = "✅" if good else "❌"
    return (f"{head} 自動補救（{path.name}）\n"
            f"對上已知模式 → 重建並重新發佈\n"
            + ("今日場次已上線：" + "、".join(after.get("live") or [])
               if good else f"仲未修好：{detail[-200:]}"))


def post_heal_result(day: str, after: dict) -> tuple[int, str] | None:
    """Render a successful republish separately from remaining data quality."""
    state = after.get("state")
    if state not in ("ok", "ok-with-advisories", "degraded"):
        return None
    live = "、".join(after.get("live") or [])
    message = f"✅ AU 體檢 {day}\n已補發佈，今日場次全部上線：{live}"
    if state == "degraded":
        message += ("\n⚠️ 發佈成功，但資料品質仍未過：\n- "
                    + "\n- ".join(after.get("issues") or []))
        return 1, message
    advisories = after.get("advisories") or []
    if advisories:
        message += ("\nbest-effort 落後（唔影響預測同發佈）：\n- "
                    + "\n- ".join(advisories))
    return 0, message


def check(day: str) -> dict:
    if run_in_progress():
        return {"state": "in-progress",
                "detail": "而家有排程 run 跑緊 —— 發佈係最後一步，仲未到"}
    live = live_meetings()
    expect = au_venues_today(day)
    scored = local_scored(day)
    if live is None:
        return {"state": "unknown", "detail": "讀唔到 live dashboard"}
    live_today = {k.split("|", 1)[1] for k in live if k.startswith(day)}
    if expect is None:
        # API 唔通就退而求其次：本機有評分而 live 冇，一樣係漏咗。
        expect = set(scored)
    missing_live = sorted(v for v in expect if v not in live_today)
    if not missing_live:
        issues, advisories = quality_issues(day)
        base = {"live": sorted(live_today), "expected": sorted(expect),
                "advisories": advisories}
        if issues:
            return {"state": "degraded", "issues": issues, **base}
        if advisories:
            # 「best-effort 項目落後」唔係 degraded：發佈同資料都過關。照出通知
            # 講件事，但退出碼要係 0，唔可以令 ./健康.sh 見到個排程好似壞咗。
            return {"state": "ok-with-advisories", **base}
        return {"state": "ok", **base}
    # 本機有冇評分？有 = 純發佈問題（補得到）；冇 = 分析根本未做（補唔到）。
    publishable = [v for v in missing_live if scored.get(v, 0) > 0]
    return {"state": "unpublished" if publishable else "unanalysed",
            "missing": missing_live, "publishable": publishable,
            "live": sorted(live_today), "expected": sorted(expect),
            "scored": scored}


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    res = check(day)
    print(json.dumps(res, ensure_ascii=False, indent=2))

    def notify(text: str):
        try:
            import au_notify
            print("通知:", au_notify.push(text) or "冇出口")
        except Exception as exc:  # noqa: BLE001
            print("通知送唔出:", exc)

    def advisory_text() -> str:
        return ("\nbest-effort 落後（唔影響預測同發佈）：\n- "
                + "\n- ".join(res.get("advisories") or [])
                if res.get("advisories") else "")

    if res["state"] in ("ok", "ok-with-advisories"):
        # 今日場次上晒線唔代表上一個 run 冇死喺第二度（例如剪走失敗、合併空殼）。
        fixed = autofix_last_failure()
        if fixed:
            print(fixed)
            notify(fixed + advisory_text())
        elif res.get("advisories"):
            notify(f"ℹ️ AU 體檢 {day}\n場次已上線、資料品質過關。"
                   + advisory_text())
        return 0
    if res["state"] == "in-progress":
        # 唔出聲。跑緊唔係問題，而為咗「有嘢報」而報就係製造雜訊。
        return 0
    if res["state"] == "degraded":
        notify(f"⚠️ AU 體檢 {day}\n場次已上線，但資料品質未過：\n- "
               + "\n- ".join(res.get("issues") or []) + advisory_text())
        return 1
    if res["state"] == "unknown":
        notify(f"⚠️ AU 體檢 {day}\n讀唔到 live dashboard —— 未能核實今日賽事有冇上線")
        return 1
    if res["state"] == "unanalysed":
        started, detail = start_analysis_recovery(day)
        if started:
            notify(f"🔄 AU 體檢 {day}\n未分析：{'、'.join(res['missing'])}\n"
                   "已自動開始一次受保護補跑；完成後會再發分析／部署結果")
            return 0
        notify(f"❌ AU 體檢 {day}\n未分析：{'、'.join(res['missing'])}\n"
               f"自動補跑冇開：{detail}\n需要人手處理")
        return 1

    notify(f"⚠️ AU 體檢 {day}\n分析做咗但冇上 dashboard：{'、'.join(res['publishable'])}\n"
           f"正在自動補發佈…")
    ok, detail = heal()
    after = check(day)
    published = post_heal_result(day, after)
    if published is not None:
        code, message = published
        notify(message)
        return code
    if after["state"] == "unanalysed":
        started, reason = start_analysis_recovery(day)
        if started:
            notify(f"🔄 AU 體檢 {day}\n補發佈後仍有未分析場次："
                   f"{'、'.join(after.get('missing', []))}\n已自動開始一次補跑")
            return 0
        detail = f"{detail}\n自動補跑冇開：{reason}"
    notify(f"❌ AU 體檢 {day}\n補發佈失敗，仲係缺：{'、'.join(after.get('missing', []))}\n"
           f"{detail[-200:]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
