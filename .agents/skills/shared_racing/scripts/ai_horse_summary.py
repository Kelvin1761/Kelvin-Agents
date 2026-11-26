#!/usr/bin/env python3
"""HKJC 賽前馬匹 AI 摘要（Hydrogen 改寫引擎報告，Python 逐匹核實後寫 sidecar JSON）。

定位（Kelvin 2026-11-26）：
  AI 只係將 `Race_<n>_Auto_Analysis.md` 改寫成每匹馬 2–3 句港式中文摘要，供 dashboard
  顯示（標「AI 摘要（未入分）」）。**AI 唔准自行分析、唔准入分、唔准引用報告以外嘅嘢。**
  Python 對照 `Race_<n>_Auto_Scoring.csv` 同報告原文逐匹核實，唔過就拒絕嗰匹。

    python3 ai_horse_summary.py --platform hkjc --meeting <dir> [--race N] [--force] [--workers 3]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DELEGATE = REPO / ".agents" / "scripts" / "codex_delegate.py"
EXTRA_PATH = ["/opt/homebrew/bin", str(Path.home() / ".local" / "bin"), "/usr/local/bin"]

PROMPT = """只可以讀取 workspace 入面嘅 `analysis.md`，唔准讀其他檔案、唔准自行分析、入分或推測報告冇寫嘅嘢。
**唔使亦唔准行任何命令**（冇得行，會令成個任務失敗）：直接用讀檔工具分段讀晒 analysis.md，寫完直接輸出，唔使自己驗證 JSON。

為 `analysis.md` 入面每一匹馬寫 2–3 句港式中文摘要（每匹 summary ≤ 90 字），必須涵蓋：
1. 報告入面嘅排名同分數
2. 最強嘅地方（對應報告 ✅ 項目）
3. 最大隱憂（對應報告 ❌ 項目；若報告寫中性 ➖ 而冇 ❌，唔好將中性項目講成隱憂，可寫暫無明顯扣分或負面訊號）

每匹馬附 2–4 條 `evidence`：必須從 `analysis.md` **逐字照抄**（每條 10–40 字），用作支持上述摘要。
所有馬號（no）、馬名（name）、排名（rank）、分數（score）必須同 `analysis.md` 完全一致；summary 入面提到嘅任何數字都要喺 `analysis.md` 出現過。

寫總分要同 score 一樣；如果提分項分數，一定要緊貼維度名（例如「同程表現 76.9 分」）。

最後**只輸出一個 JSON array**（唔好加任何解釋或前後文字），格式如下：
[{"no":8,"name":"竣誠駒","rank":1,"score":79.9,"summary":"…","evidence":["…","…"]}]
"""

SCORE_TOL = 0.06
CLAIM_TOL = 0.05  # 摘要正文寫嘅總分（一位小數）：只容四捨五入差
RETRIES = 1
MAX_SUMMARY_LEN = 120
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
RACE_ANALYSIS_RE = re.compile(r"^Race_(\d+)_Auto_Analysis\.md$")


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = ":".join(EXTRA_PATH + [env.get("PATH", "")])
    return env


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def sha256_file(path: Path | str) -> str:
    """計算檔案 SHA-256 hex digest。"""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_truth_hkjc(csv_path: Path | str) -> dict[int, dict]:
    """讀 `Race_<n>_Auto_Scoring.csv` → {horse_number: {name, rank, score}}。"""
    truth: dict[int, dict] = {}
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            raw_no = str(row.get("horse_number") or "").strip()
            if not raw_no:
                continue
            no = int(float(raw_no))
            name = str(row.get("horse_name") or "").strip()
            rank = int(float(str(row["rank"]).strip()))
            score = float(str(row["official_ranking_score"]).strip())
            truth[no] = {"name": name, "rank": rank, "score": score}
    return truth


def parse_reply(text: str) -> list[dict]:
    """由第一個 `[` 到最後一個 `]` 抽 JSON array；唔係 list 就 raise ValueError。"""
    s = (text or "").strip()
    start = s.find("[")
    end = s.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("回覆搵唔到 JSON array")
    data = json.loads(s[start : end + 1])
    if not isinstance(data, list):
        raise ValueError("JSON 頂層唔係 list")
    return data


def _norm(s: str) -> str:
    """剷走空白同 `*`、`` ` ``，用嚟比對 evidence 原文。"""
    return re.sub(r"[\s*`]+", "", str(s or ""))


def _parse_int(val) -> int | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if not math.isfinite(val) or val != int(val):
            return None
        return int(val)
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None
    return None


def _parse_float(val) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    try:
        out = float(val)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


_SECTION_RE = re.compile(r"\*\*【No\.(\d+)】")
_RANK_CLAIM_RE = re.compile(r"(?:排名?|全場)第\s*(\d+)")
_SCORE_CLAIM_RE = re.compile(r"(\d{2,3}\.\d)\s*分")
# 引擎 9D 維度（報告「##### 維度：`NN.N分`」）。摘要提分項分數要緊貼維度名，否則一律當總分核對。
DIMENSION_WORDS = ("同程", "檔位", "走位", "段速", "狀態", "穩定", "評分與經驗", "經驗", "賽績", "健康", "新鮮", "騎練", "晨操")
_PART_RE = re.compile(r"^#{2,4} \[第", re.M)  # 第三部分（最終預測）之類：唔屬於最後一匹馬


def _has_number(text: str, num: str) -> bool:
    """完整數字先算（65.0 唔當有 5、165.0 唔當有 65.0）。"""
    return re.search(r"(?<![\d.])" + re.escape(num) + r"(?![\d]|\.\d)", text) is not None


def horse_context(analysis_text: str, no: int, name: str) -> str:
    """呢匹馬自己嘅段落（【No.X】到下一匹）＋報告入面所有提到佢個名嘅行（例如全場排名表、重點）。
    Sol 2026-11-26：證據同數字要嚟自呢匹馬，唔可以借隔籬馬嘅原文。"""
    parts = []
    marks = list(_SECTION_RE.finditer(analysis_text))
    for i, m in enumerate(marks):
        if int(m.group(1)) == no:
            end = marks[i + 1].start() if i + 1 < len(marks) else len(analysis_text)
            part = _PART_RE.search(analysis_text, m.end(), end)
            end = part.start() if part else end
            parts.append(analysis_text[m.start():end])
    parts.extend(line for line in analysis_text.splitlines() if name and name in line)
    return "\n".join(parts)


def verify(rows: list, analysis_text: str, truth: dict[int, dict]) -> tuple[dict[int, dict], list[dict]]:
    """逐匹核實 AI 輸出 → (accepted_by_no, rejected_list)。"""
    parsed_nos = [_parse_int(r.get("no")) if isinstance(r, dict) else None for r in rows]
    no_counts = Counter(n for n in parsed_nos if n is not None)

    accepted: dict[int, dict] = {}
    rejected: list[dict] = []

    for row, no in zip(rows, parsed_nos):
        if not isinstance(row, dict):
            rejected.append({"no": None, "reason": "項目格式唔係 JSON object"})
            continue
        if no is None:
            rejected.append({"no": row.get("no"), "reason": "馬號格式唔啱"})
            continue
        if no_counts[no] > 1:
            rejected.append({"no": no, "reason": "馬號重複（同一馬號出現多次）"})
            continue
        if no not in truth:
            rejected.append({"no": no, "reason": "馬號唔喺評分表"})
            continue

        t = truth[no]
        name = row.get("name")
        if not isinstance(name, str) or name != t["name"]:
            rejected.append({"no": no, "reason": f"馬名唔一致（預期 {t['name']}）"})
            continue

        rank = _parse_int(row.get("rank"))
        if rank is None or rank != t["rank"]:
            rejected.append({"no": no, "reason": f"排名唔一致（預期 {t['rank']}）"})
            continue

        score = _parse_float(row.get("score"))
        if score is None or abs(score - t["score"]) > SCORE_TOL + 1e-9:
            rejected.append({"no": no, "reason": f"分數差距過大（預期 {t['score']}）"})
            continue

        context = horse_context(analysis_text, no, t["name"])
        norm_context = _norm(context)
        ev = row.get("evidence")
        if not isinstance(ev, list) or not (2 <= len(ev) <= 4):
            rejected.append({"no": no, "reason": "evidence 要有 2–4 條"})
            continue
        bad_ev = False
        for item in ev:
            if not isinstance(item, str):
                bad_ev = True
                break
            ne = _norm(item)
            if not ne or ne not in norm_context:
                bad_ev = True
                break
        if bad_ev:
            rejected.append({"no": no, "reason": "evidence 唔係呢匹馬嘅報告原文"})
            continue

        raw_summary = row.get("summary")
        if not isinstance(raw_summary, str) or not raw_summary.strip():
            rejected.append({"no": no, "reason": "summary 係空"})
            continue
        summary = raw_summary.strip()
        if len(summary) > MAX_SUMMARY_LEN:
            rejected.append({"no": no, "reason": f"summary 超過 {MAX_SUMMARY_LEN} 字"})
            continue

        missing_nums = [m.group(0) for m in NUM_RE.finditer(summary) if not _has_number(context, m.group(0))]
        if missing_nums:
            rejected.append({"no": no, "reason": f"summary 數字唔喺呢匹馬嘅報告：{'、'.join(missing_nums)}"})
            continue
        bad_rank = [c for c in _RANK_CLAIM_RE.findall(summary) if int(c) != t["rank"]]
        if bad_rank:
            rejected.append({"no": no, "reason": f"summary 講錯排名：第{bad_rank[0]}（預期 {t['rank']}）"})
            continue
        # 「NN.N分」：等於總分 OK；唔等嘅只可以係緊貼維度名嘅分項分數（前 10 字有維度名、而且呢匹馬報告有呢個數）。
        # 其餘一律當錯總分（Sol 2026-11-26：唔可以因為同馬某分項啱數就放行錯總分）。
        bad_score = []
        for m in _SCORE_CLAIM_RE.finditer(summary):
            c = m.group(1)
            if abs(float(c) - t["score"]) <= CLAIM_TOL + 1e-9:  # 只容四捨五入（79.86 → 79.9，唔准 79.8）
                continue
            before = re.split(r"[。！？；;!?，,、\n]", summary[max(0, m.start() - 10):m.start()])[-1]  # 同一分句
            if any(w in before for w in DIMENSION_WORDS) and not re.search(r"綜合|總分|9D", before) \
                    and _has_number(context, c):
                continue
            bad_score.append(c)
        if bad_score:
            rejected.append({"no": no, "reason": f"summary 講錯分數：{bad_score[0]}（預期 {t['score']}）"})
            continue
        others = [v["name"] for k, v in truth.items() if k != no and v["name"] and v["name"] not in t["name"]
                  and v["name"] in summary]
        if others:
            rejected.append({"no": no, "reason": f"summary 提到其他馬：{others[0]}"})
            continue

        accepted[no] = {
            "name": name,
            "rank": rank,
            "score": score,
            "summary": summary,
            "evidence": list(ev),
        }

    return accepted, rejected


def _run_hydrogen(analysis_path: Path) -> str:
    """用隔離 workspace 呼叫 Hydrogen (`codex_delegate.py run third`) 讀 analysis.md。"""
    analysis_path = Path(analysis_path)
    m = RACE_ANALYSIS_RE.match(analysis_path.name)
    race_tag = f"R{m.group(1)}" if m else analysis_path.stem
    title = f"AI 馬匹摘要 {analysis_path.parent.name} {race_tag}"

    with tempfile.TemporaryDirectory(prefix="ai_horse_ws_") as ws_dir, \
            tempfile.TemporaryDirectory(prefix="ai_horse_io_") as io_dir:
        ws = Path(ws_dir)
        io = Path(io_dir)
        shutil.copy2(analysis_path, ws / "analysis.md")
        brief = io / "brief.md"
        out = io / "out.md"
        brief.write_text(PROMPT, encoding="utf-8")

        cmd = [
            sys.executable,
            str(DELEGATE),
            "run",
            "third",
            "--cd",
            str(ws),
            "--prompt-file",
            str(brief),
            "--title",
            title,
            "--reply-limit",
            "4000",
            "--out",
            str(out),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=900,
                env=_env(),
            )
        except subprocess.TimeoutExpired as exc:
            stderr_tail = (exc.stderr or "").strip()[-300:] if isinstance(exc.stderr, str) else ""
            raise RuntimeError(f"Hydrogen 超時 (900s): {stderr_tail}") from exc

        reply = out.read_text(encoding="utf-8").strip() if out.exists() else ""
        if proc.returncode != 0 or not reply:
            stderr_tail = (proc.stderr or "").strip()[-300:]
            raise RuntimeError(
                f"Hydrogen 失敗 (rc={proc.returncode}): {stderr_tail or 'out 冇內容'}"
            )
        return reply


def summarise_race(meeting_dir: Path | str, race_no: int, runner=None, force: bool = False) -> dict:
    """為單場產生 `Race_<n>_AI_Summary.json`；出錯只返 status dict 唔會 raise。"""
    meeting_dir = Path(meeting_dir)
    analysis = meeting_dir / f"Race_{race_no}_Auto_Analysis.md"
    csv_path = meeting_dir / f"Race_{race_no}_Auto_Scoring.csv"
    if not analysis.exists():
        return {"status": "skipped", "reason": f"缺 {analysis.name}"}
    if not csv_path.exists():
        return {"status": "skipped", "reason": f"缺 {csv_path.name}"}

    src_sha = sha256_file(analysis)
    sidecar = meeting_dir / f"Race_{race_no}_AI_Summary.json"
    if sidecar.exists() and not force:
        try:
            prev = json.loads(sidecar.read_text(encoding="utf-8"))
            if (isinstance(prev, dict) and prev.get("source_sha256") == src_sha
                    and prev.get("scoring_sha256") == sha256_file(csv_path)):
                return {"status": "cached"}
        except (OSError, ValueError):
            pass

    runner_fn = runner or _run_hydrogen
    try:
        analysis_text = analysis.read_text(encoding="utf-8")
        truth = load_truth_hkjc(csv_path)
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
    rows, last_exc = None, None
    for _attempt in range(1 + RETRIES):  # Hydrogen 偶然想行命令被拒／JSON 爛：再試一次
        try:
            rows = parse_reply(runner_fn(analysis))
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    if rows is None:
        return {"status": "failed", "reason": f"{type(last_exc).__name__}: {last_exc}"}

    accepted, rejected = verify(rows, analysis_text, truth)
    payload = {
        "schema": 1,
        "platform": "hkjc",
        "race": int(race_no),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": analysis.name,
        "source_sha256": src_sha,
        "scoring_sha256": sha256_file(csv_path),
        "label": "AI 摘要（未入分）",
        "horses": {str(no): accepted[no] for no in sorted(accepted)},
        "rejected": rejected,
    }
    _atomic_write(sidecar, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return {"status": "ok", "accepted": len(accepted), "rejected": len(rejected)}


def summarise_meeting(
    meeting_dir: Path | str,
    platform: str = "hkjc",
    workers: int = 3,
    force: bool = False,
    runner=None,
) -> dict[int, dict]:
    """並行處理成個場次資料夾內所有 `Race_*_Auto_Analysis.md`，按場次數字排序返回。"""
    if platform != "hkjc":
        raise ValueError("暫時只支援 hkjc")

    meeting_dir = Path(meeting_dir)
    race_nos: list[int] = []
    for p in meeting_dir.glob("Race_*_Auto_Analysis.md"):
        if not p.is_file():
            continue
        m = RACE_ANALYSIS_RE.match(p.name)
        if m:
            race_nos.append(int(m.group(1)))
    race_nos.sort()
    if not race_nos:
        return {}

    max_workers = max(1, int(workers))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            rno: executor.submit(summarise_race, meeting_dir, rno, runner=runner, force=force)
            for rno in race_nos
        }
        return {rno: futures[rno].result() for rno in race_nos}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", default="hkjc", help="暫時只支援 hkjc")
    ap.add_argument("--meeting", required=True, help="場次資料夾路徑")
    ap.add_argument("--race", type=int, help="只跑指定場次")
    ap.add_argument("--force", action="store_true", help="忽略 cache 強制重做")
    ap.add_argument("--workers", type=int, default=3, help="並行線程數（預設 3）")
    args = ap.parse_args(argv)

    if args.platform != "hkjc":
        print("暫時只支援 hkjc", file=sys.stderr)
        return 1

    meeting_dir = Path(args.meeting)
    if args.race is not None:
        results = {args.race: summarise_race(meeting_dir, args.race, force=args.force)}
    else:
        results = summarise_meeting(
            meeting_dir,
            platform=args.platform,
            workers=args.workers,
            force=args.force,
        )

    for race_no, res in results.items():
        print(f"R{race_no}: {json.dumps(res, ensure_ascii=False)}")

    if results and all(res.get("status") == "failed" for res in results.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
