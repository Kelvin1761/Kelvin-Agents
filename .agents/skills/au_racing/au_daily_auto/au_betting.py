#!/usr/bin/env python3
"""Kelvin 嘅落注策略 —— 選注、更新、結算。

規則（2026-08-12 Kelvin 定）：
  * 只考慮頭兩選。
  * 賠率細過 `MIN_ODDS` 嘅唔落（唔要短賠）。
  * 兩隻都合格嗰陣：其中一隻超過 `SPREAD_ODDS` 就兩隻都落；兩隻都喺
    `MIN_ODDS`–`SPREAD_ODDS` 之間就只落首選。
  * 一隻合格就落一隻，冇合格就唔落。

⚠️ **位注**（Kelvin 2026-08-12 確認）。門檻同分水都套落**位賠**，唔係贏賠。
Sportsbet 係固定賠率，所以落注嗰刻嘅位賠就係派彩價 —— 結算精確，唔使官方位置派彩。
入位嘅定義跟真實派彩：8 匹或以上派三位、5–7 匹派兩位、4 匹或以下淨係贏。

⚠️ 平注（每注 1 個單位）。呢個係刻意：注碼一變就唔係測「揀馬準唔準」，而係測
「注碼分配」，兩件事混埋一齊就分唔清邊個帶來收益。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MIN_ODDS = 2.0      # 位賠低過呢個唔落
SPREAD_ODDS = 3.0   # 兩隻都落嘅前提：至少一隻位賠高過呢個
STAKE = 1.0
MODE = "place"      # ⚠️ 位注。改成 "win" 就係贏注 —— 但實測位注好 9pp。

RE_LABEL = re.compile(r"^## Race (\d+)\s*$\n- Performance label", re.M)
RE_TOP3 = re.compile(r"^- Model Top 3: (.+)$", re.M)
RE_HORSE = re.compile(r"#(\d+)\s+([^,#]+?)(?=,|$)")
RE_SP = re.compile(r"^(\d+)(?:st|nd|rd|th):\s*#(\d+)\s+.*?SP\$([\d.]+)", re.M)
RE_RANK = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", re.M)


def decide(picks: list[tuple[int, str, float]]) -> list[tuple[int, str, float]]:
    """[(馬號, 馬名, 賠率)]（已按排名排好）→ 應該落注嗰啲。"""
    ok = [p for p in picks[:2] if p[2] >= MIN_ODDS]
    if len(ok) < 2:
        return ok
    if max(p[2] for p in ok) > SPREAD_ODDS:
        return ok
    return ok[:1]          # 兩隻都係中短賠 —— 只落首選


def top_two(folder: Path, race_no: int) -> list[tuple[int, str]]:
    """由分析檔嘅排名表讀頭兩選。"""
    f = folder / f"Race_{race_no}_Auto_Analysis.md"
    if not f.exists():
        return []
    body = f.read_text(errors="replace")
    i = body.find("全場綜合戰力排名")
    if i < 0:
        return []
    rows = RE_RANK.findall(body[i:i + 4000])[:2]
    return [(int(n), nm.strip()) for _r, n, nm in rows]


def odds_at(folder: Path, race_no: int, which: str = "first") -> tuple[str, dict]:
    """`first` = 最早捕捉（晚更分析時）；`last` = 最新捕捉（早更）。"""
    try:
        hist = json.loads((folder / "odds_history.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", {}
    snaps = hist.get(str(race_no)) or {}
    if not snaps:
        return "", {}
    when = sorted(snaps)[0 if which == "first" else -1]
    return when, {int(k): v for k, v in snaps[when].items()}


def race_bets(folder: Path, race_no: int, which: str = "first"):
    """回 (捕捉時間, 頭兩選同其位賠, 應該落嗰啲)。

    ⚠️ 用**位賠**做篩選 —— 門檻 2.0 同分水 3.0 都係位賠。用贏賠篩會揀出完全
    唔同嘅一批馬（位賠 ≥2 大約等於贏賠 ≥5–6）。
    """
    when, prices = odds_at(folder, race_no, which)
    idx = 0 if MODE == "win" else 1
    picks = []
    for num, name in top_two(folder, race_no):
        p = prices.get(num)
        try:
            odds = float(p[idx]) if p else None
        except (TypeError, ValueError):
            odds = None
        if odds:
            picks.append((num, name, odds))
    return when, picks, decide(picks)


def meeting_bets(folder: Path, which: str = "first"):
    out, when_seen = [], set()
    races = sorted(int(m.group(1)) for m in
                   (re.search(r"Race_(\d+)_", f.name)
                    for f in folder.glob("Race_*_Auto_Analysis.md")) if m)
    for rno in races:
        when, picks, bets = race_bets(folder, rno, which)
        if when:
            when_seen.add(when.split("|")[0][:16].replace("T", " "))
        out.append({"race": rno, "picks": picks, "bets": bets})
    return out, sorted(when_seen)


def _venue(name: str) -> str:
    return re.sub(r"\s+Race\s+[\d\-]+$", "", name[11:]).strip()


def _folders(day: str):
    from wongchoi_paths import AU_RACING  # noqa: PLC0415

    root = Path(AU_RACING)
    seen = {}
    for base in (root, root / "Archive"):
        for d in base.glob(f"{day} *"):
            if d.is_dir():
                seen.setdefault(d.name, d)
    return [seen[k] for k in sorted(seen)]


def bet_list(day: str, which: str = "first") -> str | None:
    """落注單。`which='last'` = 早更更新版。"""
    blocks, n_bets, when_all = [], 0, set()
    for folder in _folders(day):
        rows, whens = meeting_bets(folder, which)
        when_all.update(whens)
        lines = []
        for r in rows:
            if not r["bets"]:
                continue
            for num, name, odds in r["bets"]:
                rank = "①" if (r["picks"] and r["picks"][0][0] == num) else "②"
                lines.append(f"R{r['race']} {rank}{name} @{odds:g}")
                n_bets += 1
        skipped = [r["race"] for r in rows if r["picks"] and not r["bets"]]
        head = f"━━ {_venue(folder.name)} ━━"
        body = lines or ["（今場冇符合條件）"]
        if skipped:
            body = body + [f"唔落：R{' R'.join(map(str, skipped))}（賠率太短）"]
        blocks.append("\n".join([head] + body))
    if not n_bets and not blocks:
        return None
    # ⚠️ 晚更嗰張係**觀察名單**，唔係落注單。Kelvin 2026-08-12 決定當朝落 ——
    # 前一晚落注等於喺唔知最終出賽名單之下鎖死價格，而退出馬會改變成場賽事嘅
    # 形勢。所以晚更嗰張要明確講「唔好落」，唔可以睇落似一張可以照抄嘅單。
    tag = "落注單（當朝定價）" if which == "last" else "觀察名單"
    head = "\n".join([
        f"💰 {tag} {day}",
        f"{n_bets} 注 · 平注 · 只落{'贏' if MODE == 'win' else '位'}",
        f"規則：頭兩選、{'贏' if MODE == 'win' else '位'}賠 ≥{MIN_ODDS:g}；"
        f"兩隻都合格但都低過 {SPREAD_ODDS:g} 就只落首選",
        ("⚠️ 呢張只係觀察 —— 唔好落，等當朝定價"
         if which == "first" else
         "⚠️ 實測 ROI 為負，建議先紙上追蹤"),
    ] + ([f"賠率取自 {sorted(when_all)[0]}"] if when_all else []))
    return head + "\n\n" + "\n\n".join(blocks)


def settle(day: str) -> str | None:
    # ⚠️ 用 `last`（當朝）嘅價結算 —— 因為落注時機係當朝。用晚更價結算會報一個
    # 你實際上冇落到嘅價。

    """結算：命中、ROI（全日同逐個馬場）。⚠️ 用賽果檔嘅 SP，所以係精確嘅。"""
    rows, tot_stake, tot_ret = [], 0.0, 0.0
    for folder in _folders(day):
        res = folder / "Race_Results_Reflector.md"
        if not res.exists():
            continue
        body = res.read_text(errors="replace")
        parts = re.split(r"^## Race (\d+)\s*$", body, flags=re.M)
        sp, finish = {}, {}
        for i in range(1, len(parts), 2):
            rno = int(parts[i])
            found = RE_SP.findall(parts[i + 1])
            sp[rno] = {int(n): float(p) for _pos, n, p in found}
            finish[rno] = {int(n): int(pos) for pos, n, _p in found}
        m_stake = m_ret = 0.0
        hits, bets = [], []
        import au_reflect_notify as _R
        for r in meeting_bets(folder, "last")[0]:
            pays = _R.places_paid(_R.field_size(folder, r["race"]))
            for num, name, odds in r["bets"]:
                m_stake += STAKE
                bets.append((r["race"], name, odds))
                fin = finish.get(r["race"], {}).get(num)
                hit = (fin == 1) if MODE == "win" else (fin is not None
                                                       and fin <= pays)
                if hit:
                    # ⚠️ 派彩用**落注嗰刻捕捉嘅位賠**（固定賠率），唔係 SP。
                    got = sp.get(r["race"], {}).get(num, odds) if MODE == "win" \
                        else odds
                    m_ret += STAKE * got
                    hits.append((r["race"], name, got, fin))
        if not m_stake:
            continue
        tot_stake += m_stake
        tot_ret += m_ret
        rows.append({"venue": _venue(folder.name), "stake": m_stake,
                     "ret": m_ret, "hits": hits, "bets": bets})
    if not tot_stake:
        return None
    def roi(r, s):
        return 100 * (r - s) / s

    out = [f"📊 落注結算 {day}",
           f"{int(tot_stake)} 注 · 中 {sum(len(r['hits']) for r in rows)} · "
           f"回收 {tot_ret:.2f} 單位",
           f"全日 ROI {roi(tot_ret, tot_stake):+.1f}%", ""]
    for r in sorted(rows, key=lambda x: -roi(x["ret"], x["stake"])):
        out.append(f"━━ {r['venue']} ━━")
        out.append(f"{int(r['stake'])} 注 · 中 {len(r['hits'])} · "
                   f"ROI {roi(r['ret'], r['stake']):+.1f}%")
        for rno, name, got, fin in r["hits"]:
            place = {1: "冠", 2: "亞", 3: "季"}.get(fin, str(fin))
            out.append(f"  ✅ R{rno} {name} {place} @{got:g}")
        won = {(h[0], h[1]) for h in r["hits"]}
        miss = [b for b in r["bets"] if (b[0], b[1]) not in won]
        if miss:
            out.append("  ❌ " + "、".join(f"R{a} {b}" for a, b, _c in miss[:6])
                       + ("…" if len(miss) > 6 else ""))
        out.append("")
    return "\n".join(out).rstrip()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "list"
    day = sys.argv[2] if len(sys.argv) > 2 else None
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    if not day:
        print("要 <mode> <YYYY-MM-DD>")
        return 2
    text = ({"list": lambda d: bet_list(d, "first"),
             "update": lambda d: bet_list(d, "last"),
             "settle": settle}[mode])(day)
    print(text or "（冇嘢好報）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
