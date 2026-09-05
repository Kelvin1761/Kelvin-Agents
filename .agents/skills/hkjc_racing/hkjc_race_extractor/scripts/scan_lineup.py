#!/usr/bin/env python3
"""比對「HKJC 而家嘅出賽名單」同「我哋分析嗰陣嘅名單」。

點解要有呢個：`run_prerace` 排喺 21:30 / 23:30 / 00:30 / 08:00 / 11:00（悉尼）。
香港頭場大約 13:00 HK = 15:00 悉尼，即係**最後一次掃描喺開賽前 4 個鐘，
成個賽日冇任何覆蓋**。香港退出馬好多喺賽日早上先公布，所以板上可以一路
掛住一隻已經退出嘅馬做首選。

呢個 module 只負責**偵測**，唔會改檔、唔會重跑。呼叫者攞到 diff 之後
自己決定重跑邊個場次。

⚠️ 設計上最重要嗰條：**抓唔到 ≠ 名單變咗**。
2026-09-05 有個故障就係將自己嘅 code bug 當成「來源未 ready」報出去。
所以呢度抓取失敗一律回 `error`，而 `changed` 一定係 False —— 一個
timeout 唔可以被讀成「成場馬退晒」而觸發重跑同通知。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
RACECARD_SCRIPT = SKILL_DIR / "extract_racecard.py"
FORMGUIDE_SCRIPT = SKILL_DIR / "extract_formguide_playwright.py"

# ⚠️ 邊個來源話事：**賽績（formguide）**，唔係排位表。
# `inject_hkjc_fact_anchors.parse_hkjc_formguide()` 個馬匹迴圈食嘅係
# `* Race N 賽績.md`，排程亦係咁 call；排位表淨係補父系／見習騎師減磅。
# 成條鏈係 賽績 → Facts → Logic → 板面。
#
# 2026-09-05 呢個 module 最初比對排位表，後果係：排位表出咗退出馬 → 偵測到
# → 重跑 → 重跑由賽績砌名單 → 隻馬仲喺度 → 下次掃描又偵測到，永遠唔收斂，
# 而板上一直掛住隻已退出嘅馬。所以權威來源一定要同重建鏈用同一個檔。
#
# 排位表照掃，但只做第二意見：兩邊唔一致通常代表 HKJC 更新有時差，
# 值得講出嚟，但唔可以用嚟決定重跑。

_NUM = re.compile(r"^馬號:\s*(\d+)\s*$", re.M)
_HORSE_BLOCK = re.compile(r"^馬號:\s*(\d+)\s*$\n^馬名:\s*(.+?)\s*$", re.M)


def parse_lineup(markdown: str) -> dict[int, str]:
    """由排位表 markdown 抽 `{馬號: 馬名}`。

    要拎名唔淨係拎號，因為「換馬」（同一個馬號換咗另一隻馬）同「退出」一樣
    需要重跑，但只比對號碼係睇唔到嘅。
    """
    return {int(num): name for num, name in _HORSE_BLOCK.findall(markdown or "")}


def lineup_looks_complete(markdown: str, lineup: dict[int, str]) -> bool:
    """每個 `馬號:` 都要配到一個 `馬名:`。

    防嘅係一個半截／殘缺嘅頁被讀成「有幾隻馬唔見咗」。
    """
    return bool(lineup) and len(_NUM.findall(markdown or "")) == len(lineup)


def logic_lineup(logic_path: Path) -> dict[int, str]:
    """由 `Race_N_Logic.json` 攞返我哋分析嗰陣用嘅名單。"""
    data = json.loads(Path(logic_path).read_text(encoding="utf-8"))
    out: dict[int, str] = {}
    for key, horse in (data.get("horses") or {}).items():
        try:
            num = int(key)
        except (TypeError, ValueError):
            continue
        out[num] = str(horse.get("horse_name") or "").strip()
    return out


def diff_lineup(current: dict[int, str], analysed: dict[int, str]) -> dict:
    """`current` 對 `analysed` 嘅差異。名字唔同 = 換馬。"""
    scratched = sorted(set(analysed) - set(current))
    added = sorted(set(current) - set(analysed))
    replaced = sorted(
        num for num in set(current) & set(analysed)
        if current[num] and analysed[num] and current[num] != analysed[num]
    )
    return {
        "scratched": [{"no": n, "horse": analysed[n]} for n in scratched],
        "added": [{"no": n, "horse": current[n]} for n in added],
        "replaced": [{"no": n, "was": analysed[n], "now": current[n]} for n in replaced],
        "changed": bool(scratched or added or replaced),
    }


def _fetch(script: Path, url: str, timeout: int) -> tuple[str, str]:
    """回 `(markdown, error)`；抓唔到就 markdown 係空而 error 有嘢。"""
    try:
        result = subprocess.run(
            [sys.executable, str(script), url],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return "", f"{type(exc).__name__}: {exc}"
    if result.returncode != 0:
        return "", f"extractor exit={result.returncode}: {(result.stderr or '')[:160]}"
    return result.stdout or "", ""


def _lineup_from(script: Path, url: str, label: str, timeout: int) -> tuple[dict, str]:
    """抓一個來源並解析成 `{馬號: 馬名}`。任何唔穩陣嘅情況一律回 error。"""
    markdown, error = _fetch(script, url, timeout)
    if error:
        return {}, f"{label}：{error}"
    lineup = parse_lineup(markdown)
    if not lineup_looks_complete(markdown, lineup):
        return {}, f"{label}唔完整（{len(lineup)} 匹解析得到）"
    return lineup, ""


def scan_race(racecard_url: str, logic_path: Path, formguide_url: str = "") -> dict:
    """一場嘅掃描結果。`changed` 只會喺真係比對得成功嗰陣先為 True。

    權威來源係**賽績**（見 module 開頭）。排位表只做第二意見：兩邊唔一致
    會寫入 `source_disagreement`，但唔會影響 `changed`。
    """
    out = {"changed": False, "error": "", "scratched": [], "added": [],
           "replaced": [], "source_disagreement": ""}
    if not Path(logic_path).exists():
        out["error"] = "未有 Logic，未分析過"
        return out
    try:
        analysed = logic_lineup(Path(logic_path))
    except (OSError, ValueError) as exc:
        out["error"] = f"Logic 讀唔到：{type(exc).__name__}"
        return out
    if not analysed:
        out["error"] = "Logic 冇馬匹紀錄"
        return out

    # 賽績 = 權威。抓唔到就乜都唔做 —— 唔可以退而求其次用排位表，
    # 因為重建鏈唔會睇排位表，咁樣會觸發一個永遠唔收斂嘅重跑。
    if not formguide_url:
        out["error"] = "冇賽績 URL，唔可以判斷"
        return out
    current, error = _lineup_from(FORMGUIDE_SCRIPT, formguide_url, "賽績", 120)
    if error:
        out["error"] = error
        return out

    out.update(diff_lineup(current, analysed))
    out.setdefault("source_disagreement", "")

    # 第二意見：排位表通常更快反映退出馬。唔一致 = HKJC 兩邊有時差，
    # 值得講，但唔會改變上面個判斷。
    if racecard_url:
        card, card_error = _lineup_from(RACECARD_SCRIPT, racecard_url, "排位表", 60)
        if not card_error and card != current:
            only_card = sorted(set(current) - set(card))
            only_form = sorted(set(card) - set(current))
            bits = []
            if only_card:
                bits.append("排位表已經冇：" + "、".join(
                    f"{n} {current[n]}" for n in only_card))
            if only_form:
                bits.append("排位表多咗：" + "、".join(
                    f"{n} {card[n]}" for n in only_form))
            out["source_disagreement"] = "；".join(bits) or "兩個來源馬名唔一致"
    return out


def verify_applied(logic_path: Path, changes: dict) -> str:
    """重跑之後確認 Logic 真係跟咗。回 "" = 已反映，否則回原因。

    ⚠️ 呢個係唯一擋得住「重跑成功但改動冇入到」嘅嘢。`run_prerace` 回 0 只
    代表條 pipeline 行完，唔代表隻退出馬真係唔見咗 —— 而如果重建鏈用緊
    另一個來源（2026-09-05 就係咁），佢會次次回 0 而次次冇改到嘢。
    """
    try:
        after = logic_lineup(Path(logic_path))
    except (OSError, ValueError) as exc:
        return f"重跑後讀唔到 Logic：{type(exc).__name__}"
    if not after:
        return "重跑後 Logic 冇馬匹紀錄"
    still = [f"{i['no']} {i['horse']}" for i in changes.get("scratched") or []
             if i["no"] in after]
    if still:
        return "重跑後仍然喺 Logic 入面：" + "、".join(still)
    unswapped = [f"{i['no']} {i['was']}" for i in changes.get("replaced") or []
                 if after.get(i["no"]) == i["was"]]
    if unswapped:
        return "重跑後仍然係舊馬：" + "、".join(unswapped)
    missing = [f"{i['no']} {i['horse']}" for i in changes.get("added") or []
               if i["no"] not in after]
    if missing:
        return "重跑後新馬仲未入到：" + "、".join(missing)
    return ""


def describe(changes: dict[int, dict]) -> str:
    """砌一句人睇得明嘅摘要（Telegram 用）。"""
    lines = []
    for race in sorted(changes):
        d = changes[race]
        bits = []
        for item in d.get("scratched") or []:
            bits.append(f"退出 {item['no']} {item['horse']}")
        for item in d.get("added") or []:
            bits.append(f"新增 {item['no']} {item['horse']}")
        for item in d.get("replaced") or []:
            bits.append(f"換馬 {item['no']} {item['was']}→{item['now']}")
        if bits:
            lines.append(f"R{race}：" + "、".join(bits))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="掃描 HKJC 出賽名單變動")
    ap.add_argument("--base_url", required=True)
    ap.add_argument("--races", required=True, help="'1-10' 或 '1,3,5'")
    ap.add_argument("--meeting_dir", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sys.path.insert(0, str(SKILL_DIR))
    from batch_extract import derive_urls, parse_races

    meeting_dir = Path(args.meeting_dir)
    result = {"changes": {}, "errors": {}}
    for race in parse_races(args.races):
        racecard_url, formguide_url = derive_urls(args.base_url, race)
        scan = scan_race(racecard_url, meeting_dir / f"Race_{race}_Logic.json",
                         formguide_url=formguide_url)
        if scan["error"]:
            result["errors"][race] = scan["error"]
        elif scan["changed"]:
            result["changes"][race] = scan
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["changes"]:
            print(describe({int(k): v for k, v in result["changes"].items()}))
        else:
            print("名單冇變動")
        for race, err in sorted(result["errors"].items()):
            print(f"⚠️ R{race} 掃唔到：{err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
