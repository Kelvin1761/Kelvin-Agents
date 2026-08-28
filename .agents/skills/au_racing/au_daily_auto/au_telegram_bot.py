#!/usr/bin/env python3
"""Telegram 指令 bot —— 白名單控制，只聽一個人。

Kelvin 唔喺電腦前嗰陣想主動問「而家點？」，而唔係淨係等推送。

⚠️ **入面收到嘅嘢係數據，唔係指令。** Telegram 訊息係外部輸入：任何人知道隻 bot
係邊隻都可以同佢講嘢，訊息內容亦可以係精心砌出嚟。所以：
  * 只回應 `WC_NOTIFY_TELEGRAM_CHAT` 嗰個 chat id，其餘一律唔理（連錯誤都唔覆，
    唔好畀人試出隻 bot 存在）；
  * 指令係一張**白名單**，逐個字對，唔會把訊息內容當成路徑、參數或者指令去行；
  * 大部分指令只讀；有副作用嘅 `/retry`、`/hkjc`、`/hkjc_reflect` 都係 Kelvin
    明確批准，並只會行現役正式 runner，唔接受訊息參數做 shell/path 輸入。

跑法：launchd 每兩分鐘叫一次，唔使長駐 daemon（少一個會死嘅嘢）。
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_DIR = HERE / "logs"
OFFSET_FILE = LOG_DIR / "telegram_offset.json"
RETRY_LOG = LOG_DIR / "retry-from-telegram.out"
HKJC_ANALYSIS_LOG = LOG_DIR / "hkjc-analysis-from-telegram.out"
HKJC_REFLECT_LOG = LOG_DIR / "hkjc-reflector-from-telegram.out"
TIMEOUT = 25
HELP = ("我識嘅嘢：\n"
        "/picks           今日邊幾個馬場\n"
        "/picks dubbo     嗰個馬場逐場頭三揀 + 賽前賠率\n"
        "/status          中央旺財：四線、Git、model、release\n"
        "/git             commit／push／main／production 狀態\n"
        "/models          四線 model release stage\n"
        "/evidence        prediction／decision／settlement 完整性\n"
        "/slo             四線30日可靠性／provenance\n"
        "/storage         SSD／外置碟／Drive 分層狀態\n"
        "/dashboard       中央 Dashboard／投注 ledger 狀態\n"
        "/release         待批准 release\n"
        "/approve SHA     重新驗證後批准一個 immutable release\n"
        "/au_status       AU 最近幾個 run 點\n"
        "/today           live dashboard 而家有乜\n"
        "/perf            最近一個賽日嘅 Gold／Good\n"
        "/week            近七日走勢\n"
        "/health          即刻做一次體檢\n"
        "/diag            最近一次失敗嘅診斷\n"
        "/retry           補跑抽取（抽唔齊嗰陣用）\n"
        "/hkjc            強制分析最新 HKJC racecard\n"
        "/hkjc_reflect    抽賽果、覆盤並更新 HKJC dashboard\n"
        "/help            呢個")


def api(method: str, **params):
    tok = os.environ.get("WC_NOTIFY_TELEGRAM_TOKEN", "")
    if not tok:
        return None
    data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/{method}",
                                 data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001
        return None


def runs(n: int = 4) -> list[dict]:
    out = []
    for f in sorted(LOG_DIR.glob("run-*.json"), key=lambda p: p.stat().st_mtime,
                    reverse=True)[:n]:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def cmd_au_status() -> str:
    rs = runs()
    if not rs:
        return "仲未有任何 run 記錄"
    icon = {"ok": "✅", "partial": "⚠️", "failed": "❌", "running": "⏳"}
    lines = []
    for d in rs:
        dep = d.get("cloudflare_deployment") or {}
        dep_s = ("冇行到" if not dep else "跳過" if dep.get("skipped")
                 else "成功" if dep.get("ok") else "失敗")
        lines.append(
            f"{icon.get(d.get('status'), '•')} {d.get('started_at', '')[5:16]} "
            f"{'晚更' if d.get('mode') == 'evening' else '早更'} "
            f"{d.get('status')} · {round((d.get('duration_seconds') or 0)/60)}分 "
            f"· 發佈{dep_s} · 錯誤{len(d.get('errors') or [])}")
    return "\n".join(lines)


def _central_repo_root() -> Path:
    configured = os.environ.get("WC_PRIMARY_REPO_ROOT")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else HERE.parents[3]
    )


def _central_payload() -> dict:
    repo = _central_repo_root()
    skills = repo / ".agents" / "skills"
    if str(skills) not in sys.path:
        sys.path.insert(0, str(skills))
    from shared_wong_choi.central_status import collect_status  # noqa: PLC0415

    state = Path(
        os.environ.get(
            "WONGCHOI_CONTROL_STATE_ROOT",
            Path.home() / "WongChoiData" / "WongChoiControl",
        )
    )
    production = _central_production_roots()
    return collect_status(repo, state, production_roots=production)


def _central_production_roots() -> dict[str, Path]:
    production = {}
    for domain in ("au", "hkjc", "tennis", "nba"):
        value = os.environ.get(f"WC_{domain.upper()}_PRODUCTION_ROOT")
        if value:
            production[domain] = Path(value)
    return production


def cmd_status() -> str:
    repo = _central_repo_root()
    skills = repo / ".agents" / "skills"
    if str(skills) not in sys.path:
        sys.path.insert(0, str(skills))
    from shared_wong_choi.central_status import render_telegram  # noqa: PLC0415

    return render_telegram(_central_payload())


def cmd_git() -> str:
    payload = _central_payload()["git"]
    primary = payload["primary"]
    lines = [
        "🧾 Wong Choi Git",
        f"primary：{primary.get('branch') or '?'} {(primary.get('head') or '?')[:12]}",
        f"dirty {len(primary.get('dirty_paths') or [])} · "
        f"pushed {'係' if primary.get('pushed') else '否'} · "
        f"main {'係' if primary.get('merged_to_main') else '否'}",
    ]
    for name, item in payload.get("production", {}).items():
        lines.append(
            f"{name.upper()} production：{item.get('status')} · "
            f"{(item.get('head') or '?')[:12]}"
        )
    return "\n".join(lines)


def cmd_models() -> str:
    lines = ["🧠 Wong Choi Models"]
    for name, item in _central_payload()["domains"].items():
        model = item.get("model_release") or {}
        stage = model.get("release_stage") or "未登記"
        commit = str(model.get("code_commit") or "?")[:12]
        lines.append(f"{name.upper()}：{stage} · {commit}")
    lines.append("NBA live evidence未齊時只會顯示pending，唔會扮production-ready。")
    return "\n".join(lines)


def cmd_evidence() -> str:
    evidence = _central_payload()["evidence"]
    counts = evidence.get("counts") or {}
    lines = [
        f"🔗 Evidence：{evidence.get('status')}",
        f"model {counts.get('model_release', 0)} · prediction {counts.get('prediction', 0)}",
        f"decision {counts.get('decision', 0)} · settlement {counts.get('settlement', 0)}",
    ]
    if evidence.get("errors"):
        lines.append("錯誤：" + "；".join(evidence["errors"][:3]))
    return "\n".join(lines)


def cmd_slo() -> str:
    reliability = _central_payload()["reliability"]
    lines = [f"📈 Wong Choi 30日SLO：{reliability.get('status')}"]
    for name, item in reliability.get("domains", {}).items():
        ratio = item.get("availability")
        shown = "no_data" if ratio is None else f"{ratio:.1%}"
        lines.append(
            f"{name.upper()}：{shown} · {item.get('slots', 0)} slots · "
            f"retry救回 {item.get('recovered_by_retry', 0)}"
        )
    provenance = (
        (reliability.get("evidence") or {}).get("production_provenance") or {}
    )
    ratio = provenance.get("ratio")
    lines.append(
        "Production provenance："
        + ("no_data" if ratio is None else f"{ratio:.1%}")
    )
    return "\n".join(lines)


def cmd_storage() -> str:
    repo = _central_repo_root()
    skills = repo / ".agents" / "skills"
    if str(skills) not in sys.path:
        sys.path.insert(0, str(skills))
    from shared_wong_choi.storage_status import (  # noqa: PLC0415
        collect_storage_status,
        render_storage_telegram,
    )

    state = Path(
        os.environ.get(
            "WONGCHOI_CONTROL_STATE_ROOT",
            Path.home() / "WongChoiData" / "WongChoiControl",
        )
    )
    return render_storage_telegram(collect_storage_status(repo, state))


def cmd_dashboard() -> str:
    repo = _central_repo_root()
    skills = repo / ".agents" / "skills"
    if str(skills) not in sys.path:
        sys.path.insert(0, str(skills))
    from shared_wong_choi.dashboard_status import (  # noqa: PLC0415
        collect_dashboard_status,
        render_dashboard_telegram,
    )

    state = Path(
        os.environ.get(
            "WONGCHOI_CONTROL_STATE_ROOT",
            Path.home() / "WongChoiData" / "WongChoiControl",
        )
    )
    return render_dashboard_telegram(collect_dashboard_status(repo, state))


def cmd_release() -> str:
    pending = _central_payload()["releases"]["pending_approval"]
    if not pending:
        return "✅ 冇 release 等緊批准"
    lines = [f"🟡 {len(pending)} 個 release 等緊批准"]
    for item in pending[:8]:
        lines.append(
            f"· {(item.get('commit') or '?')[:12]} {item.get('risk')} "
            f"{item.get('branch')}"
        )
    return "\n".join(lines)


def cmd_approve(arg: str = "") -> str:
    selector = arg.strip()
    if not re.fullmatch(r"[0-9a-f]{12,64}", selector):
        return "格式：/approve 12位或以上小寫 commit SHA"
    repo = _central_repo_root()
    skills = repo / ".agents" / "skills"
    if str(skills) not in sys.path:
        sys.path.insert(0, str(skills))
    from shared_wong_choi.release_approval import approve_release  # noqa: PLC0415
    from shared_wong_choi.release_activation import activate_release  # noqa: PLC0415
    from shared_wong_choi.release_manager import ReleaseError  # noqa: PLC0415

    state = Path(
        os.environ.get(
            "WONGCHOI_CONTROL_STATE_ROOT",
            Path.home() / "WongChoiData" / "WongChoiControl",
        )
    )
    try:
        result = approve_release(
            repo,
            state,
            selector=selector,
            actor="telegram:authorised-chat",
            notify=True,
        )
    except ReleaseError as exc:
        return f"⛔ 批准失敗：{exc}"
    try:
        activation = activate_release(
            repo,
            state,
            selector=selector,
            actor="telegram:authorised-chat",
            production_roots=_central_production_roots(),
            notify=True,
        )
    except ReleaseError as exc:
        return (
            f"🟡 {(result.get('commit') or selector)[:12]} 已merge，但未部署：{exc}\n"
            "中央status會保持 activation pending/failed，唔會扮完成。"
        )
    if result["status"] == "already_merged" and activation["status"] == "already_active":
        return f"✅ {(result.get('commit') or selector)[:12]} 已經merge及部署，冇重複副作用"
    return (
        f"✅ 已批准、merge及部署 {(result.get('commit') or selector)[:12]}\n"
        "每一步都有immutable event；重覆指令冇副作用。"
    )


def cmd_today() -> str:
    d = _live()
    if d is None:
        return "攞唔到 live dashboard"
    lines = [f"live 更新時間 {(d.get('meta') or {}).get('generated_at', '?')[:16]}"]
    for m in d.get("meetings") or []:
        key = f"{m.get('date')}|{m.get('venue')}"
        entry = (d.get("races") or {}).get(key) or {}
        n = len(next(iter((entry.get("races_by_analyst") or {}).values()), []))
        lines.append(f"· {m.get('date')} {m.get('venue')} — {n} 場")
    return "\n".join(lines)


def cmd_perf() -> str:
    from wongchoi_paths import AU_RACING  # noqa: PLC0415

    arch = Path(AU_RACING) / "Archive"
    reports = sorted(arch.glob("*/*_Reflector_Report.md"),
                     key=lambda p: p.stat().st_mtime, reverse=True)[:9]
    if not reports:
        return "仲未有覆盤報告"
    day = reports[0].parent.name[:10]
    tot = {"Gold": 0, "Good": 0, "Pass": 0, "Miss": 0, "races": 0}
    rows = []
    for r in reports:
        if not r.parent.name.startswith(day):
            continue
        b = r.read_text(errors="replace")
        g = lambda k: int(m.group(1)) if (m := re.search(rf"^- {k}: (\d+)$", b, re.M)) else 0
        n = len(re.findall(r"^- Performance label", b, re.M))
        vals = {k: g(k) for k in ("Gold", "Good", "Pass", "Miss")}
        tot["races"] += n
        for k in vals:
            tot[k] += vals[k]
        rows.append(f"· {r.parent.name[11:].rsplit(' Race', 1)[0]}: "
                    f"Gold {vals['Gold']} Good {vals['Good']} / {n} 場")
    if not tot["races"]:
        return "最近嗰個賽日仲未覆盤完"
    head = (f"🏇 {day} · {tot['races']} 場\n"
            f"Gold {tot['Gold']} ({100*tot['Gold']/tot['races']:.0f}%) · "
            f"Good {tot['Good']} · Pass {tot['Pass']} · Miss {tot['Miss']}")
    return head + "\n" + "\n".join(rows)




def _live() -> dict | None:
    """攞 live dashboard。⚠️ 兩樣缺一不可：

    * **User-Agent** —— Cloudflare 對 urllib 預設嗰個 UA 回 403。體檢嗰邊一直有設
      所以行得，呢度冇設就成日攞唔到，而 `except` 把 403 吞埋，表面上淨係見到
      「攞唔到 live dashboard」，睇極都唔知係俾人擋咗。
    * **cache-buster** —— 唔加就會讀到 edge 舊副本，啱啱發佈完會顯示成未發佈。
    """
    url = ("https://wongchoi-dashboard.pages.dev/dashboard-data.json"
           f"?cb={int(datetime.now().timestamp()*1000)}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "WongChoi-Bot/1.0",
        "Cache-Control": "no-cache, max-age=0", "Pragma": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001
        return None


def _odds(day: str, venue: str, race_no: int) -> dict[int, tuple[str, str]]:
    """{馬號: (贏賠, 位賠)}，由本機 Formguide 讀。⚠️ 係**分析嗰陣**捕捉嘅市場價，
    唔係開跑價 —— 所以標「賽前」，唔可以扮成 SP。"""
    from wongchoi_paths import AU_RACING  # noqa: PLC0415

    root = Path(AU_RACING)
    for base in (root, root / "Archive"):
        for d in base.glob(f"{day} {venue}*"):
            fg = next(iter(d.glob(f"*Race {race_no} Formguide.md")), None)
            if not fg:
                continue
            body = fg.read_text(errors="replace")
            starts = [(m.start(), int(m.group(1)))
                      for m in re.finditer(r"^\[(\d+)\]\s", body, re.M)]
            out = {}
            for i, (pos, num) in enumerate(starts):
                end = starts[i + 1][0] if i + 1 < len(starts) else len(body)
                m = re.search(r"WinOdds:\s*([\d.]+|-)\s+PlcOdds:\s*([\d.]+|-)",
                              body[pos:end])
                if m:
                    out[num] = (m.group(1), m.group(2))
            return out
    return {}


def cmd_picks(arg: str = "") -> str:
    d = _live()
    if not d:
        return "攞唔到 live dashboard"
    today = datetime.now().strftime("%Y-%m-%d")
    ms = [m for m in d.get("meetings") or [] if m.get("date") >= today]
    if not ms:
        ms = d.get("meetings") or []
    if not arg:
        lines = ["揀一個馬場，例：/picks dubbo", ""]
        for m in ms:
            key = f"{m['date']}|{m['venue']}"
            n = len(next(iter((d["races"].get(key, {}).get("races_by_analyst")
                               or {}).values()), []))
            lines.append(f"· {m['date']} {m['venue']} — {n} 場")
        return "\n".join(lines)

    want = re.sub(r"[^a-z]", "", arg.lower())
    hit = next((m for m in ms
                if want in re.sub(r"[^a-z]", "", m["venue"].lower())), None)
    if not hit:
        return f"搵唔到「{arg[:20]}」。而家有：" + "、".join(m["venue"] for m in ms)
    key = f"{hit['date']}|{hit['venue']}"
    races = next(iter((d["races"].get(key, {}).get("races_by_analyst")
                       or {}).values()), [])
    lines = [f"🏇 {hit['date']} {hit['venue']} · {len(races)} 場", ""]
    for r in sorted(races, key=lambda x: x.get("race_number") or 0):
        rno = r.get("race_number")
        od = _odds(hit["date"], hit["venue"], rno)
        head = f"R{rno}" + (f" {r.get('distance')}" if r.get("distance") else "")
        lines.append(head)
        for p in (r.get("top_picks") or [])[:3]:
            num = p.get("horse_number")
            w, pl = od.get(num, ("", ""))
            price = f"  賽前 贏${w} 位${pl}" if w and w != "-" else ""
            lines.append(f"  {PICKMARK.get(p.get('rank'), '·')}{p.get('horse_name')}"
                         f" ({p.get('grade') or '?'}){price}")
    return "\n".join(lines)


def cmd_diag() -> str:
    """最近一個失敗／partial run 嘅診斷。手機睇短版，完整版落檔。"""
    import au_diagnose
    hist = au_diagnose.runs()
    if not hist:
        return "冇 run 記錄"
    target = next((r for r in hist if r.get("status") in ("failed", "partial")), None)
    if not target:
        return "✅ 最近幾個 run 都冇失敗"
    text = au_diagnose.diagnose(target, hist)
    au_diagnose.BUNDLE.write_text(text, encoding="utf-8")
    return au_diagnose.phone_summary(text)


def cmd_retry() -> str:
    """補跑抽取。Kelvin 明確要求（2026-08-11 網絡斷咗令五個場次冇分析）。

    ⚠️ 呢個係唯一一個有副作用嘅指令，所以三道限制：
      * 只有已授權 chat 叫得到（`main()` 已經擋咗其他人）；
      * **有 run 跑緊就唔開** —— 兩個 run 同時郁同一批 folder、同一個 Chrome
        profile、同一個 dashboard，正正係把鎖要防嗰件事；
      * 唔會重抽已經分析好嘅場次（`skipped_already_analysed` 即刻跳過），
        所以就算亂叫幾次都唔會浪費網絡配額。
    唔會自己改 code、唔會發佈任何未驗證嘅嘢 —— 佢行嘅係同排程一樣嗰條路。
    """
    import subprocess

    sys.path.insert(0, str(HERE))
    import au_healthcheck

    if au_healthcheck.run_in_progress():
        return "⏳ 而家有 run 跑緊 —— 唔開第二個（會同佢爭同一批資料）"
    runner = HERE / "run_au_daily_schedule.sh"
    if not runner.exists():
        return "搵唔到 runner"
    out = RETRY_LOG
    try:
        # 新 worktree／剛重裝時未必跑過 daily job，logs/ 仍然可以唔存在。
        # `/retry` 唔應該因為純粹欠一個可安全建立嘅目錄而失敗。
        out.parent.mkdir(parents=True, exist_ok=True)
        # detach：bot 每兩分鐘就會退出，唔可以由佢等成個 run。
        with out.open("w") as fh:
            subprocess.Popen(
                ["/bin/zsh", str(runner), "evening", "--skip-review",
                 "--rounds", "3", "--round-gap", "420"],
                stdout=fh, stderr=fh, start_new_session=True)
    except Exception as exc:  # noqa: BLE001
        return f"開唔到：{type(exc).__name__}: {exc}"
    return ("▶️ 已開始補跑抽取（唔會重抽已分析嘅場次）\n"
            "做完會照樣推「新分析已完成」同發佈結果。\n"
            "想睇進度打 /status")


def _hkjc_runner() -> Path:
    configured = os.environ.get("WC_PRIMARY_REPO_ROOT")
    primary = Path(configured).expanduser() if configured else Path.home() / "Antigravity-repo"
    relative = Path(
        ".agents/skills/hkjc_racing/hkjc_daily_auto/run_hkjc_daily_schedule.sh"
    )
    candidate = primary / relative
    return candidate if candidate.exists() else HERE.parents[3] / relative


def _start_hkjc(mode: str, *, log_path: Path, force: bool = False) -> str:
    """Start a fixed HKJC production mode; Telegram text never reaches argv."""
    import fcntl
    import subprocess

    runner = _hkjc_runner()
    if not runner.exists():
        return "搵唔到 HKJC runner"
    lock_path = runner.parent / "state" / "hkjc_daily_state.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "⏳ HKJC automation 而家有 run 跑緊，唔開第二個"

    command = ["/bin/bash", str(runner), mode]
    if force:
        command.append("--force")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as handle:
            subprocess.Popen(
                command,
                stdout=handle,
                stderr=handle,
                start_new_session=True,
            )
    except Exception as exc:  # noqa: BLE001
        return f"開唔到 HKJC：{type(exc).__name__}: {exc}"
    return "started"


def cmd_hkjc() -> str:
    result = _start_hkjc("prerace", log_path=HKJC_ANALYSIS_LOG, force=True)
    if result != "started":
        return result
    return (
        "▶️ 已開始 HKJC 最新賽日正式分析。\n"
        "Racecard／formguide 未齊會保留 pending 並自動補跑；完成後會 Telegram 通知及更新 dashboard。"
    )


def cmd_hkjc_reflect() -> str:
    result = _start_hkjc("postrace", log_path=HKJC_REFLECT_LOG)
    if result != "started":
        return result
    return (
        "▶️ 已開始 HKJC 賽後流程。\n"
        "會抽正式賽果、對齊 prediction snapshot、跑 reflector，並移除 dashboard 已完成賽日。"
    )


def cmd_health() -> str:
    import subprocess
    try:
        r = subprocess.run(["/usr/bin/python3", str(HERE / "au_healthcheck.py")],
                           capture_output=True, text=True, timeout=900)
        d = json.loads(r.stdout.split("\n通知")[0])
    except Exception as exc:  # noqa: BLE001
        return f"體檢行唔到：{type(exc).__name__}: {exc}"
    state = d.get("state")
    if state == "ok":
        return "✅ 體檢正常 —— 今日場次全部上線：" + "、".join(d.get("live") or [])
    if state == "in-progress":
        return "⏳ 而家有排程 run 跑緊，發佈係最後一步 —— 遲啲再查"
    advisory = ("\nbest-effort 落後（唔影響預測同發佈）：\n- "
                + "\n- ".join(d.get("advisories") or [])
                if d.get("advisories") else "")
    if state == "ok-with-advisories":
        return ("✅ 體檢正常 —— 今日場次全部上線："
                + "、".join(d.get("live") or []) + advisory)
    if state == "degraded":
        return "⚠️ 體檢：場次已上線但資料品質未過\n- " + \
            "\n- ".join(d.get("issues") or []) + advisory
    return f"⚠️ 體檢：{state}\n缺：" + "、".join(d.get("missing") or [])


def cmd_week() -> str:
    """近七日逐日 Gold／Good 走勢。"""
    from wongchoi_paths import AU_RACING  # noqa: PLC0415

    days: dict[str, dict] = {}
    for rep in (Path(AU_RACING) / "Archive").glob("*/*_Reflector_Report.md"):
        day = rep.parent.name[:10]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            continue
        b = rep.read_text(errors="replace")
        n = len(re.findall(r"^- Performance label", b, re.M))
        if not n:
            continue
        acc = days.setdefault(day, {"races": 0, "Gold": 0, "Good": 0})
        acc["races"] += n
        for k in ("Gold", "Good"):
            m = re.search(rf"^- {k}: (\d+)$", b, re.M)
            acc[k] += int(m.group(1)) if m else 0
    if not days:
        return "仲未有覆盤報告"
    lines = ["📈 近期逐日表現（Gold = 前三全喺頭四揀）", ""]
    for day in sorted(days)[-7:]:
        a = days[day]
        g = 100 * a["Gold"] / max(a["races"], 1)
        bar = "█" * round(g / 5)
        lines.append(f"{day}  {a['races']:>3}場  Gold {a['Gold']:>2} ({g:>4.0f}%) "
                     f"Good {a['Good']:>2}  {bar}")
    return "\n".join(lines)


PICKMARK = {1: "①", 2: "②", 3: "③"}

COMMANDS = {"/status": cmd_status, "/git": cmd_git, "/models": cmd_models,
            "/evidence": cmd_evidence, "/slo": cmd_slo,
            "/storage": cmd_storage, "/dashboard": cmd_dashboard,
            "/release": cmd_release,
            "/au_status": cmd_au_status,
            "/today": cmd_today, "/perf": cmd_perf,
            "/health": cmd_health, "/week": cmd_week, "/diag": cmd_diag,
            "/retry": cmd_retry, "/hkjc": cmd_hkjc,
            "/hkjc_reflect": cmd_hkjc_reflect,
            "/help": lambda: HELP, "/start": lambda: HELP}
# 收參數嘅指令要另外列 —— 白名單仍然係逐個字對，參數只當文字用嚟配對馬場名，
# 永遠唔會變成路徑或者指令。
COMMANDS_WITH_ARG = {"/picks": cmd_picks, "/approve": cmd_approve}


def _record_unknown(chat: dict, text: str) -> None:
    """把未授權嘅 chat 記落本機，方便日後決定加唔加做收件人。"""
    path = LOG_DIR / "unknown_chats.json"
    try:
        seen = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    cid = str(chat.get("id") or "")
    if not cid:
        return
    entry = seen.setdefault(cid, {"first_seen": None, "messages": 0})
    entry["messages"] += 1
    entry["name"] = " ".join(x for x in (chat.get("first_name"),
                                         chat.get("last_name")) if x) or None
    entry["username"] = chat.get("username")
    entry["last_text"] = text[:60]
    entry["first_seen"] = entry["first_seen"] or datetime.now().isoformat(
        timespec="seconds")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seen, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def load_offset() -> int:
    try:
        return int(json.loads(OFFSET_FILE.read_text(encoding="utf-8"))["offset"])
    except (OSError, ValueError, KeyError):
        return 0


def save_offset(v: int) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": v}), encoding="utf-8")


def main() -> int:
    allowed = os.environ.get("WC_NOTIFY_TELEGRAM_CHAT", "")
    if not allowed or not os.environ.get("WC_NOTIFY_TELEGRAM_TOKEN"):
        print("冇設 WC_NOTIFY_TELEGRAM_TOKEN / _CHAT —— 唔行")
        return 0
    d = api("getUpdates", offset=load_offset(), timeout=0)
    if not d or not d.get("ok"):
        return 0
    handled = 0
    for u in d.get("result") or []:
        save_offset(u["update_id"] + 1)
        msg = u.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id") or "")
        if chat_id != str(allowed):
            # 唔識嘅人：**唔覆**。覆一句「你唔准」等於話畀人知隻 bot 存在。
            # 但要**記低**：之前係靜靜咁掉咗，於是 Kelvin 根本唔知有邊個試過，
            # 想加一個朋友做收件人嘅時候亦攞唔返個 chat id（poller 已經 confirm
            # 咗嗰條 update，queue 清空）。記錄只落本機檔案。
            _record_unknown(msg.get("chat") or {}, msg.get("text") or "")
            continue
        # ⚠️ 逐個字對白名單。訊息內容永遠唔會變成路徑、參數或者指令。
        parts = (msg.get("text") or "").strip().split()
        head = parts[0].lower() if parts else ""
        fn = COMMANDS.get(head)
        fn_arg = COMMANDS_WITH_ARG.get(head)
        try:
            if fn:
                reply = fn()
            elif fn_arg:
                reply = fn_arg(" ".join(parts[1:])[:40])
            else:
                reply = f"唔識「{(msg.get('text') or '')[:30]}」\n\n{HELP}"
        except Exception as exc:  # noqa: BLE001
            reply = f"行嗰陣出錯：{type(exc).__name__}: {exc}"
        api("sendMessage", chat_id=chat_id, text=reply[:3900],
            disable_web_page_preview=True)
        handled += 1
    print(f"處理咗 {handled} 條")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(HERE.parents[3]))
    raise SystemExit(main())
