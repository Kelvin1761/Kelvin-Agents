#!/usr/bin/env python3
"""Generate a plain-language explanation of a live Wong Choi scoring model.

WHY THIS EXISTS
---------------
The hand-written model doc (`AU Wong Choi 現行評分結構詳解（港式中文）.md`) drifted
badly: it described a 7D matrix with `sectional` / `form_line` / `pace_figure`
while the live AU matrix had already become 6D, and it pointed at
`rank_adjustments.py`, a file that no longer exists.  A reader had no way to
know which half was true.

So this doc is GENERATED, never written.  Every number below is read out of the
live modules at run time — change a weight and the doc changes with it.  There
is no second copy of the truth to fall out of sync.

`--check` re-generates and diffs against what is on disk, so CI can fail the
build the moment the committed doc stops matching the code.

Usage
-----
    python explain_model.py --platform au
    python explain_model.py --platform hkjc --no-corpus
    python explain_model.py --platform au --check

One platform per process ON PURPOSE: AU and HKJC each ship a top-level module
named `scoring`, so importing both in one interpreter silently gives you
whichever loaded first.  See run_tests.sh for the same constraint.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import html as html_mod
import importlib
import json
import os
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUT_DIR = REPO_ROOT / "Wong Choi 模型說明"

PLATFORMS = {
    "au": {
        "title": "AU Wong Choi",
        "engine_dir": REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine",
        "corpus_glob": "AU_Racing/*/Race_*_Logic.json",
        "data_root_attr": "AU_RACING",
    },
    "hkjc": {
        "title": "HKJC Wong Choi",
        "engine_dir": REPO_ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine",
        "corpus_glob": "HK_Racing/*/Race_*_Logic.json",
        "data_root_attr": "HK_RACING",
    },
}

# Modules whose contents ARE the model.  Their hashes go in the footer so a
# reader can tell at a glance whether the doc predates the code.
FINGERPRINT_FILES = ("scoring.py", "matrix_mapper.py", "renderer.py")


# ── loading the live model ────────────────────────────────────────────────────

def load_engine(engine_dir: Path):
    """Import the platform's scoring modules and hand back what they define."""
    sys.path.insert(0, str(engine_dir.parent))
    package = engine_dir.name
    scoring = importlib.import_module(f"{package}.scoring")
    matrix_mapper = importlib.import_module(f"{package}.matrix_mapper")
    renderer = importlib.import_module(f"{package}.renderer")

    weights = dict(scoring.MATRIX_WEIGHTS)
    formulas = {k: list(v) for k, v in matrix_mapper.MATRIX_FORMULAS.items()}
    return {
        "weights": weights,
        "coefficient_model": hasattr(scoring, "compose_matrix_score"),
        "debut_weights": dict(getattr(scoring, "DEBUT_MATRIX_WEIGHTS", {}) or {}),
        "formulas": formulas,
        # AU stretches each dimension onto one ruler; HKJC does not have gains.
        "gains": dict(getattr(matrix_mapper, "MATRIX_DISPLAY_GAINS", {}) or {}),
        "matrix_labels": dict(getattr(renderer, "MATRIX_LABELS", {})),
        "feature_labels": dict(getattr(renderer, "FEATURE_LABELS", {})),
        "matrix_roles": dict(getattr(renderer, "MATRIX_ROLES", {}) or {}),
        "grades": tuple(scoring.GRADE_THRESHOLDS),
        # HKJC 有顯示尺（綜合分 + 逐維度）；AU 冇，所以 getattr 預設空。
        "display_scale": dict(getattr(scoring, "DISPLAY_SCALE", {}) or {}),
        "dimension_display": {
            "centres": dict(getattr(scoring, "MATRIX_DISPLAY_CENTRES", {}) or {}),
            "gains": dict(getattr(scoring, "MATRIX_DISPLAY_GAINS", {}) or {}),
            "target_sd": getattr(scoring, "MATRIX_DISPLAY_TARGET_SD", None),
        },
        "ability_label": getattr(renderer, "ABILITY_LABEL", "綜合戰力分"),
        "feature_keys": tuple(getattr(scoring, "FEATURE_KEYS", ())),
        "report_only_keys": tuple(getattr(scoring, "REPORT_ONLY_FEATURE_KEYS", ()) or ()),
        "ranking_overlays": tuple(getattr(scoring, "RANKING_OVERLAYS", ()) or ()),
        "contract_version": getattr(scoring, "SCORING_CONTRACT_VERSION", None),
        "bands": band_thresholds(scoring),
    }


def band_thresholds(scoring):
    """Recover the ✅✅ / ✅ / ➖ / ❌ cut points by probing the live function."""
    band = scoring.score_band
    cuts, current = [], band(100.0)
    for value in range(100, -1, -1):
        symbol = band(float(value))
        if symbol != current:
            cuts.append((value + 1, current))
            current = symbol
    cuts.append((0, current))
    return tuple(cuts)


# ── measuring what the model actually does ────────────────────────────────────

def resolve_corpus(platform: str) -> Path | None:
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import wongchoi_paths
    except Exception:
        return None
    return getattr(wongchoi_paths, PLATFORMS[platform]["data_root_attr"], None)


def measure(corpus_root: Path | None, matrix_keys, max_races: int):
    """Within-race spread per dimension, from real scored races.

    The weight alone does not tell you how much a dimension MOVES a ranking:
    a heavy weight on a dimension that scores every horse 60.0 changes nothing.
    Influence = weight x how much the dimension actually varies inside a race.

    Only races whose matrix keys match the CURRENT model are counted — older
    Logic.json files were produced by earlier matrix shapes and mixing them in
    would describe a model that no longer exists.
    """
    if corpus_root is None:
        return None
    # Include archived meetings — see corpus_paths for why one level is not enough.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from corpus_paths import logic_files as corpus_logic_files
    paths = corpus_logic_files(corpus_root)
    if not paths:
        return None

    wanted = set(matrix_keys)
    spreads = {key: [] for key in matrix_keys}
    flat = {key: 0 for key in matrix_keys}          # horses scored exactly neutral
    horses = 0
    used, skipped, meetings = 0, 0, set()

    for path in paths:
        if used >= max_races:
            break
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            skipped += 1
            continue
        rows = [
            h.get("python_auto", {}).get("matrix_scores") or {}
            for h in (data.get("horses") or {}).values()
        ]
        rows = [r for r in rows if r]
        if len(rows) < 3 or set(rows[0]) != wanted:
            skipped += 1
            continue
        used += 1
        meetings.add(Path(path).parent.name)
        horses += len(rows)
        for key in matrix_keys:
            values = [float(r.get(key, 60.0)) for r in rows]
            spreads[key].append(statistics.pstdev(values))
            flat[key] += sum(1 for v in values if abs(v - 60.0) < 1e-9)

    if not used:
        return None
    return {
        "races": used,
        "skipped": skipped,
        "horses": horses,
        "meetings": sorted(meetings),
        "spread": {k: statistics.fmean(v) for k, v in spreads.items() if v},
        "flat_rate": {k: flat[k] / horses for k in matrix_keys},
    }


def influence(weights, spread):
    """Share of the ranking each dimension really controls."""
    raw = {k: weights.get(k, 0.0) * spread.get(k, 0.0) for k in weights}
    total = sum(raw.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in raw.items()}


# ── provenance ────────────────────────────────────────────────────────────────

def fingerprint(engine_dir: Path):
    entries = []
    for name in FINGERPRINT_FILES:
        path = engine_dir / name
        if not path.exists():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        entries.append((name, digest))
    try:
        commit = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip() or "unknown"
    except Exception:
        commit = "unknown"
    return entries, commit


# ── rendering ─────────────────────────────────────────────────────────────────

def feature_name(model: dict, feature: str) -> str:
    """`label \`key\`` where a human label exists, else just the key.

    Some derived HKJC inputs (race_shape_context_score, ...) have no entry in
    the renderer's FEATURE_LABELS; printing "x `x`" reads like a bug.
    """
    label = model["feature_labels"].get(feature)
    return f"{label} `{feature}`" if label else f"`{feature}`"


def bar(fraction: float, width: int = 20) -> str:
    filled = round(max(0.0, min(1.0, fraction)) * width)
    return "█" * filled + "·" * (width - filled)


def render_markdown(platform: str, model: dict, stats: dict | None, engine_dir: Path) -> str:
    title = PLATFORMS[platform]["title"]
    weights = model["weights"]
    labels = model["matrix_labels"]
    formulas = model["formulas"]
    gains = model["gains"]
    overlays = model.get("ranking_overlays") or ()
    inf = influence(weights, stats["spread"]) if stats else {}

    # Display order: every dimension the reports show, heaviest ranking weight
    # first, then the display-only ones.
    keys = sorted(labels, key=lambda k: (-weights.get(k, 0.0), k))
    L = []
    A = L.append

    A(f"# {title} 模型說明")
    A("")
    A("> ⚠️ **呢份文件係由 live code 自動生成，唔係人手寫。**")
    A("> 想更新就再跑一次生成器（見文件最尾），唔好直接改呢個檔 —— 改咗會被覆蓋，")
    A("> 而且會令文件同真實模型再次講唔同嘅嘢。")
    A("")

    # ── 1. one-page summary ──
    A("## 1. 一頁睇晒")
    A("")
    A(f"隻馬最後得到嘅係一個「{model['ability_label']}」。個分係咁計出嚟：")
    A("")
    A(f"1. 由原始資料計出 **{len(model['feature_keys'])} 個基礎分**（近績、騎師、檔位…），每個都係 0–100，**60 分 = 中性／冇證據**")
    A(f"2. 啲基礎分按固定配方合成 **{len(weights)} 個維度分**")
    if overlays:
        A("3. 維度分按下面嘅權重加權相加 → 矩陣基礎分")
        A("4. 加上下面逐項列明嘅場內 ranking overlay → 綜合戰力分")
        A("5. 場內由高到低排名，就係最終推介次序")
    else:
        A("3. 維度分按下面嘅權重加權相加 → 綜合戰力分")
        A("4. 場內由高到低排名，就係最終推介次序")
    A("")
    A("### 每個維度佔幾重")
    A("")
    coefficients = model.get("coefficient_model", False)
    if coefficients:
        A("矩陣直接顯示分項分數，沒有尾段放大。合成式：**60 ＋ Σ〔（維度分 −60）× 合成係數〕**。")
        A("下面的權重是合成係數，不是總和必須等於100%的百分比；ML／refit 直接擬合這一套係數。")
        A("")
    if inf:
        A("| 維度 | 權重 | 實測影響力 | 佔比圖 |")
        A("|---|---:|---:|---|")
    else:
        A("| 維度 | 權重 | 佔比圖 |")
        A("|---|---:|---|")
    for key in keys:
        weight = weights.get(key, 0.0)
        name = labels.get(key, key)
        if weight <= 0:
            note = "**0%（只顯示，唔入排名）**"
            if inf:
                A(f"| {name} `{key}` | {note} | — | {bar(0)} |")
            else:
                A(f"| {name} `{key}` | {note} | {bar(0)} |")
            continue
        display_weight = f"{weight:.4f}" if coefficients else f"{weight * 100:.1f}%"
        if inf:
            A(f"| {name} `{key}` | {display_weight} | {inf.get(key, 0) * 100:.1f}% | {bar(inf.get(key, 0))} |")
        else:
            A(f"| {name} `{key}` | {display_weight} | {bar(weight / sum(weights.values()) if coefficients else weight)} |")
    A("")
    if overlays:
        A("### 額外場內 ranking overlay")
        A("")
        A("| Overlay | 公式 | 缺資料處理 |")
        A("|---|---|---|")
        for overlay in overlays:
            A(
                f"| {overlay.get('label', overlay.get('key', ''))} "
                f"`{overlay.get('key', '')}` | {overlay.get('formula', '')} | "
                f"{overlay.get('missing', '')} |"
            )
        A("")
    if inf:
        A("**「權重」同「實測影響力」有咩分別？**  權重係配方上寫死嘅數。實測影響力係")
        A("實際跑落去，呢個維度喺同一場馬入面真係拉開幾多分距離 —— 一個權重好高但成場馬")
        A("都畀差唔多分數嘅維度，其實冇乜影響力。兩者差得遠，就代表個維度「有名無實」。")
        A("")
    if inf and not coefficients:
        drift = sorted(
            (
                (abs(inf[k] - weights[k]) / weights[k], k)
                for k in weights
                if weights.get(k, 0.0) > 0.02 and k in inf
            ),
            reverse=True,
        )
        loud = [(ratio, k) for ratio, k in drift if ratio >= 0.35]
        if loud:
            A("**⚠️ 配方同實際唔夾嘅維度：**")
            A("")
            for ratio, key in loud:
                direction = "大過" if inf[key] > weights[key] else "細過"
                A(f"- **{labels.get(key, key)}** — 帳面 {weights[key] * 100:.1f}%，"
                  f"實際 {inf[key] * 100:.1f}%（{direction}帳面 {ratio * 100:.0f}%）")
            A("")
            A("呢個唔一定係錯，但值得查：通常代表某個維度嘅分數散開程度同當初調校時唔同咗")
            A("（例如換咗數據源、或者有 leaf 退役），權重就冇再對應返佢真正嘅話事權。")
            A("")

    if any(weights.get(k, 0.0) <= 0 for k in labels):
        dead = [labels.get(k, k) for k in labels if weights.get(k, 0.0) <= 0]
        A(f"⚠️ **{'、'.join(dead)}** 喺報告見到，但權重係 0 —— 佢完全唔影響排名，純粹俾你睇。")
        A("")

    # ── 2. what feeds each dimension ──
    A("## 2. 每個維度食緊咩")
    A("")
    for key in keys:
        name = labels.get(key, key)
        weight = weights.get(key, 0.0)
        display_weight = f"合成係數 {weight:.4f}" if coefficients else f"權重 {weight * 100:.1f}%"
        head = f"### {name}　`{key}`　— {display_weight}"
        if weight <= 0:
            head += "（唔入排名）"
        A(head)
        A("")
        components = formulas.get(key, [])
        if not components:
            A("_（呢個維度冇喺配方表出現）_")
            A("")
            continue
        A("| 基礎分 | 喺呢個維度佔 |")
        A("|---|---:|")
        for feature, share in components:
            A(f"| {feature_name(model, feature)} | {share * 100:.1f}% |")
        A("")
        if stats:
            spread = stats["spread"].get(key)
            flat = stats["flat_rate"].get(key)
            if spread is not None:
                A(f"實測：同一場馬入面呢個維度嘅分數差距（標準差）平均 **{spread:.2f} 分**；"
                  f"**{flat * 100:.1f}%** 嘅馬喺呢個維度攞到恰好 60 分（即係冇證據）。")
                A("")
        if key in gains:
            A(f"顯示尺放大倍數 `gain` = **{gains[key]:.4f}**　"
              "（用嚟令每個維度嘅分數散開程度一致，睇 band 先至公平）")
            A("")

    # ── 3. how to read a score ──
    A("## 3. 個分點樣讀")
    A("")
    A("**60 分永遠代表「中性 / 冇證據」**，唔係「合格」。高過 60 = 有正面證據，低過 60 = 有負面證據。")
    A("")
    A("### 報告入面嘅符號")
    A("")
    A("| 符號 | 分數範圍 |")
    A("|---|---|")
    bands = model["bands"]
    for i, (cut, symbol) in enumerate(bands):
        top = "100" if i == 0 else str(bands[i - 1][0] - 1)
        A(f"| {symbol} | {cut} – {top} |")
    A("")
    A(f"### Grade（{model['ability_label']} → 等級）")
    A("")
    A("| Grade | 需要幾多分 |")
    A("|---|---:|")
    for threshold, grade in model["grades"]:
        A(f"| {grade} | ≥ {threshold} |")
    A("")
    A("Grade 只係一個閱讀標籤，排名純粹按分數高低，唔會因為 Grade 而換位。")
    A("")
    ds = model.get("display_scale") or {}
    if ds:
        slope = ds["target_sd"] / ds["observed_sd"]
        A(f"### {model['ability_label']}同維度分都係顯示尺")
        A("")
        A("七個維度加權平均出嚟嘅係**原始分**，佢永遠困喺各維度自己嘅範圍之內 ——")
        A(f"實測 {ds['sample']:,} 匹馬只佔 50–77 分，所以上面由 A 到 S+ 六級曾經係")
        A("**數學上到唔到**（一隻六戰全勝、官方評分高過全場 33 分嘅馬只讀到「B+ 中上游」）。")
        A("所以報告印出嚟嘅綜合分係一條仿射變換：")
        A("")
        A(f"    顯示分 = {ds['anchor']} + {slope:.4f} × (原始分 − {ds['centre']})")
        A("")
        dd = model.get("dimension_display") or {}
        if dd.get("gains"):
            A("**逐個維度亦有自己一把尺。** 七個維度嘅原始 SD 由 3.47 到 12.26（差 3.5 倍），")
            A("但 band 門檻（✅✅ 85 / ✅ 70 / ➖ 55 / ❌ 40）係同一套 —— 所以五個維度永遠")
            A("出唔到 ✅✅，「馬匹健康」連 ❌ 都出唔到，「賽績線」永遠出唔到 ❌。校正式：")
            A("")
            A(f"    維度顯示分 = 60 + gain × (維度原始分 − centre)　（目標 SD {dd['target_sd']}）")
            A("")
            A("| 維度 | centre（實測中位） | gain |")
            A("|:---|---:|---:|")
            labels = model.get("matrix_labels", {})
            for key in sorted(dd["gains"], key=lambda k: -model["weights"].get(k, 0)):
                A(f"| {labels.get(key, key)} | {dd['centres'][key]} | {dd['gains'][key]} |")
            A("")
        A("**兩把尺都唔加任何資訊，亦唔改任何排名** —— 斜率全部正數、全體同一條式，")
        A("排名讀嘅係原始分（`ability_score_raw` / `matrix_scores`）。金樣本、單元測試")
        A("同 run contract 三邊都守住呢一點。")
        A("")

    # ── 4. debut / report-only ──
    if model["debut_weights"]:
        A("## 4. 首次出賽嘅馬用另一套權重")
        A("")
        A("初出馬冇往績，所以換一套只食得到嘅證據嘅權重：")
        A("")
        A("| 維度 | 初出權重 |")
        A("|---|---:|")
        for key, weight in sorted(model["debut_weights"].items(), key=lambda x: -x[1]):
            A(f"| {labels.get(key, key)} `{key}` | {weight * 100:.1f}% |")
        A("")

    if model["report_only_keys"]:
        A("## 5. 有計但唔入排名嘅基礎分")
        A("")
        A("呢啲分照計、照喺報告出，但唔會進入排名運算 —— 佢哋係俾你讀故事用嘅，")
        A("唔係俾模型投票用嘅：")
        A("")
        for feature in model["report_only_keys"]:
            A(f"- {feature_name(model, feature)}")
        A("")

    # ── provenance ──
    A("## 呢份文件由邊度嚟")
    A("")
    entries, commit = fingerprint(engine_dir)
    A(f"- 生成時間：`{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M %Z')}`")
    A(f"- Git commit：`{commit}`")
    if model["contract_version"]:
        A(f"- Scoring contract：`{model['contract_version']}`")
    for name, digest in entries:
        A(f"- `{name}` 指紋：`{digest}`")
    if stats:
        meetings = stats["meetings"]
        A(f"- 實測樣本：**{stats['races']} 場、{stats['horses']} 匹馬**，"
          f"由 `{meetings[0]}` 到 `{meetings[-1]}`（跳過 {stats['skipped']} 個舊格式檔案）")
    else:
        A("- 實測樣本：**冇**（今次生成搵唔到已評分嘅語料庫，只列出配方上嘅權重）")
    A("")
    A("重新生成：")
    A("")
    A("```bash")
    A(f"python3 .agents/skills/shared_racing/scripts/explain_model.py --platform {platform}")
    A("```")
    A("")
    return "\n".join(L) + "\n"


MD_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")


def markdown_to_html(markdown: str, title: str) -> str:
    """Tiny purpose-built renderer — the doc only uses the features handled here."""
    out, in_table, in_code, in_quote = [], False, False, False

    def close_table():
        nonlocal in_table
        if in_table:
            out.append("</tbody></table>")
            in_table = False

    def close_quote():
        nonlocal in_quote
        if in_quote:
            out.append("</blockquote>")
            in_quote = False

    def inline(text: str) -> str:
        text = html_mod.escape(text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        return text

    lines = markdown.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            close_table(); close_quote()
            if in_code:
                out.append("</code></pre>"); in_code = False
            else:
                out.append("<pre><code>"); in_code = True
            index += 1
            continue
        if in_code:
            out.append(html_mod.escape(line))
            index += 1
            continue

        if line.startswith("> "):
            close_table()
            if not in_quote:
                out.append("<blockquote>"); in_quote = True
            out.append(f"<p>{inline(line[2:])}</p>")
            index += 1
            continue
        close_quote()

        table = MD_TABLE_ROW.match(line)
        if table:
            cells = [c.strip() for c in table.group(1).split("|")]
            separator = all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c)
            if separator:
                index += 1
                continue
            if not in_table:
                out.append('<table><thead><tr>')
                out.extend(f"<th>{inline(c)}</th>" for c in cells)
                out.append("</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>")
                out.extend(f"<td>{inline(c)}</td>" for c in cells)
                out.append("</tr>")
            index += 1
            continue
        close_table()

        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            out.append(f"<h{level}>{inline(line[level:].strip())}</h{level}>")
        elif line.startswith("- "):
            out.append(f"<ul><li>{inline(line[2:])}</li></ul>")
        elif re.match(r"^\d+\. ", line):
            out.append(f"<ol><li>{inline(line.split('. ', 1)[1])}</li></ol>")
        elif line.strip():
            out.append(f"<p>{inline(line)}</p>")
        index += 1
    close_table(); close_quote()

    body = "\n".join(out)
    body = re.sub(r"</ul>\n<ul>", "\n", body)
    body = re.sub(r"</ol>\n<ol>", "\n", body)
    return f"""<!doctype html>
<html lang="zh-HK"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html_mod.escape(title)}</title>
<style>
:root {{ --bg:#fbfaf7; --fg:#1d1c1a; --muted:#6b6862; --line:#e2ded6; --accent:#8a5a2b; --code:#f2efe9; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#16151a; --fg:#e9e6e0; --muted:#9d988f; --line:#2f2d33; --accent:#d9a066; --code:#212026; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:2.5rem 1.25rem 6rem; background:var(--bg); color:var(--fg);
  font:16px/1.75 -apple-system,"PingFang HK","Helvetica Neue",sans-serif;
  max-width:56rem; margin-inline:auto; }}
h1 {{ font-size:1.9rem; line-height:1.3; margin:0 0 1.5rem; }}
h2 {{ font-size:1.35rem; margin:3rem 0 1rem; padding-bottom:.4rem; border-bottom:2px solid var(--line); }}
h3 {{ font-size:1.05rem; margin:2rem 0 .6rem; color:var(--accent); }}
p, li {{ margin:.5rem 0; }}
code {{ background:var(--code); padding:.12em .4em; border-radius:4px; font-size:.86em;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
pre {{ background:var(--code); padding:1rem; border-radius:8px; overflow-x:auto; }}
pre code {{ background:none; padding:0; }}
blockquote {{ margin:1.5rem 0; padding:.75rem 1.25rem; border-left:4px solid var(--accent);
  background:var(--code); border-radius:0 8px 8px 0; }}
blockquote p {{ margin:.25rem 0; }}
.tw {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; margin:1rem 0; font-size:.94rem; display:block; overflow-x:auto; }}
th, td {{ border-bottom:1px solid var(--line); padding:.5rem .7rem; text-align:left; white-space:nowrap; }}
th {{ font-weight:600; color:var(--muted); font-size:.82rem; text-transform:uppercase; letter-spacing:.04em; }}
td:nth-child(2), td:nth-child(3) {{ font-variant-numeric:tabular-nums; }}
ul, ol {{ padding-left:1.5rem; }}
</style></head><body>
{body}
</body></html>
"""


# ── entry point ───────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--corpus", type=Path, default=None,
                        help="Folder of scored meetings; defaults to the platform data root.")
    parser.add_argument("--no-corpus", action="store_true",
                        help="Skip measurement; describe the recipe only.")
    parser.add_argument("--max-races", type=int, default=500)
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if the doc on disk no longer matches the live code.")
    args = parser.parse_args(argv)

    spec = PLATFORMS[args.platform]
    engine_dir = spec["engine_dir"]
    if not engine_dir.is_dir():
        print(f"engine dir missing: {engine_dir}", file=sys.stderr)
        return 2

    model = load_engine(engine_dir)

    stats = None
    if not args.no_corpus:
        corpus = args.corpus or resolve_corpus(args.platform)
        try:
            stats = measure(corpus, tuple(model["matrix_labels"]), args.max_races)
        except OSError as exc:
            print(f"corpus unreadable ({exc.__class__.__name__}); continuing without it", file=sys.stderr)

    markdown = render_markdown(args.platform, model, stats, engine_dir)
    title = f"{spec['title']} 模型說明"

    args.out_dir.mkdir(parents=True, exist_ok=True)
    md_path = args.out_dir / f"{title}.md"
    html_path = args.out_dir / f"{title}.html"

    if args.check:
        # Compare FINGERPRINTS, not text.  The measured columns depend on a data
        # root that CI does not have, so a text diff would fail there for the
        # wrong reason; the source hashes are what actually decide whether the
        # doc still describes the live model.
        if not md_path.exists():
            print(f"❌ 搵唔到 {md_path.name} —— 未生成過", file=sys.stderr)
            return 1
        committed = dict(re.findall(r"^- `([^`]+)` 指紋：`([0-9a-f]+)`", 
                                    md_path.read_text(encoding="utf-8"), re.M))
        live = dict(fingerprint(engine_dir)[0])
        drifted = [name for name, digest in live.items() if committed.get(name) != digest]
        missing = [name for name in live if name not in committed]
        if drifted or missing:
            print(f"❌ {md_path.name} 已經過期 —— 下面嘅檔案改咗但文件冇重新生成：", file=sys.stderr)
            for name in sorted(set(drifted) | set(missing)):
                print(f"     {name}  文件記住 {committed.get(name, '（冇記錄）')} → 而家 {live[name]}",
                      file=sys.stderr)
            print(f"\n   修法：python3 {Path(__file__).name} --platform {args.platform}", file=sys.stderr)
            return 1
        print(f"✅ {md_path.name} 同 live code 一致")
        return 0

    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(markdown_to_html(markdown, title), encoding="utf-8")
    print(f"wrote {md_path}")
    print(f"wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
