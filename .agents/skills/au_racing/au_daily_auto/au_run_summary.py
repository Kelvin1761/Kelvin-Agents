#!/usr/bin/env python3
"""兩條人真係想睇嘅推送。

`morning`：退出馬、場地狀況變化、排名有冇郁。開跑前你想知嘅就係呢三樣。
`evening`：新一日嘅分析做好咗、上咗線冇。

⚠️ 兩條都只喺**真係有嘢講**嗰陣先發。冇變動嗰朝仍然出一條「一切照舊」係製造
雜訊，而雜訊嘅代價係你開始無視通知 —— 跟住真出事嗰次就會漏咗。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _venue(name: str) -> str:
    return name[11:].rsplit(" Race", 1)[0]


def morning(run: dict) -> str | None:
    scratch = run.get("scratchings_detected") or []
    track = run.get("track_changes_detected") or []
    changes = run.get("analysis_changes") or []
    # ⚠️ 「冇郁」同「冇查過」係兩件事。舊 run 冇 `ranking_moved` 呢個 key（排名
    # 捕捉 2026-08-10 先加），報「頭三揀冇郁」等於畀一個假保證。
    tracked = [c for c in changes if "ranking_moved" in c]
    moved = [(c["meeting"], m) for c in tracked for m in (c["ranking_moved"] or [])]
    if not (scratch or track or moved):
        return None

    lines = [f"🌅 早更覆核 {run.get('review_day', '')}"]

    if scratch:
        by_meet: dict[str, list[str]] = {}
        for s in scratch:
            bits = []
            if s.get("scratched"):
                bits.append("退出 #" + "、#".join(s["scratched"]))
            if s.get("emergencies_in"):
                bits.append("後備入替 #" + "、#".join(s["emergencies_in"]))
            if bits:
                by_meet.setdefault(_venue(s["meeting"]), []).append(
                    f"R{s['race']} {' / '.join(bits)}")
        if by_meet:
            lines.append("\n🐴 出賽名單變動")
            for venue, items in by_meet.items():
                lines.append(f"· {venue}：" + "；".join(items[:6])
                             + ("…" if len(items) > 6 else ""))

    if track:
        seen: dict[str, set] = {}
        for c in track:
            a, b = (c["change"] + ["", ""])[:2]
            a = "／".join(a) if isinstance(a, list) else a
            seen.setdefault(_venue(c["meeting"]), set()).add(f"{a} → {b}")
        lines.append("\n🌦 場地狀況")
        for venue, moves in seen.items():
            lines.append(f"· {venue}：" + "、".join(sorted(moves)))

    lines.append("\n📊 排名")
    if moved:
        for meeting, m in moved[:8]:
            lines.append(f"· {_venue(meeting)} R{m['race']}")
            lines.append(f"    前：{' / '.join(m['before'])}")
            lines.append(f"    後：{' / '.join(m['after'])}")
        if len(moved) > 8:
            lines.append(f"  （另有 {len(moved)-8} 場有變）")
    elif tracked:
        lines.append("· 重評分之後頭三揀冇郁")
    else:
        lines.append("· （呢個 run 未有記錄排名前後對比）")
    return "\n".join(lines)


def evening(run: dict) -> str | None:
    added = run.get("races_added") or []
    if not added:
        return None
    dep = run.get("cloudflare_deployment") or {}
    live = (dep.get("verified") or {}).get("ok")
    total = sum(len(r.get("races") or []) for r in added)
    lines = [f"🆕 新分析已完成 · {len(added)} 個馬場 / {total} 場", ""]
    for r in sorted(added, key=lambda x: x["meeting"]):
        n = len(r.get("races") or [])
        going = r.get("going") or "—"
        flag = "" if r.get("complete", True) else "  ⚠️ 未齊"
        lines.append(f"· {_venue(r['meeting'])} — {n} 場 · {going}{flag}")
    lines.append("")
    if dep.get("skipped"):
        lines.append("發佈：冇變動，唔使發")
    elif live:
        lines.append("✅ 已上線並核實 —— dashboard 睇得到")
    elif dep.get("ok"):
        lines.append("⚠️ 發佈完成但核實唔到，體檢會跟進")
    else:
        lines.append("❌ 未發佈得到 —— 體檢會嘗試補發")
    return "\n".join(lines)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "morning"
    path = sys.argv[2] if len(sys.argv) > 2 else None
    if path:
        run = json.loads(Path(path).read_text(encoding="utf-8"))
    else:
        files = sorted((HERE / "logs").glob(f"run-{mode}-*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            print("冇 run 記錄")
            return 1
        run = json.loads(files[0].read_text(encoding="utf-8"))
    text = (morning if mode == "morning" else evening)(run)
    if not text:
        print("冇嘢好講 —— 唔發")
        return 0
    print(text)
    if "--send" in sys.argv:
        sys.path.insert(0, str(HERE))
        import au_notify
        print("\n送出：", au_notify.push(text) or "冇出口")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
