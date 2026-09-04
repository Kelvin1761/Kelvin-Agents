#!/usr/bin/env python3
"""AU 橫向查：用 2026-09-04 喺 HKJC 側捉到嘅五個缺陷形狀去掃 AU。

形狀（全部真係喺呢個 repo 出現過，唔係假設）：
  S1 有 reader 冇 writer      —— hkjc_results_db 有 5 個讀者、零個寫者
  S2 硬抄咗一份引擎常數        —— EXPECTED_FEATURES["au"] 停留喺 10 個 key
  S3 精確字串比對應該用 glob   —— 晨操檔案數、FROZEN_DIRNAMES
  S4 欄位寫得出但永遠係空      —— speedmaps= / odds= 冇 caller 傳
  S5 單向守衛                  —— 只查「閘門有冇引擎唔識嘅 key」

唯讀。冇 exit code 語義（0 = 掃完），報告畀人睇。
"""
from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AU_ROOTS = [
    REPO / ".agents/skills/au_racing",
    REPO / ".agents/skills/shared_racing",
    REPO / ".agents/skills/shared_wong_choi",
]


def au_files() -> list[Path]:
    out: list[Path] = []
    for root in AU_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if "/archive/" in str(p).lower() or "__pycache__" in str(p):
                continue
            out.append(p)
    return sorted(out)


def rel(p: Path) -> str:
    return str(p.relative_to(REPO))


FILES = au_files()
SRC = {p: p.read_text(encoding="utf-8", errors="replace") for p in FILES}
TREE: dict[Path, ast.AST] = {}
for p, s in SRC.items():
    try:
        TREE[p] = ast.parse(s)
    except SyntaxError:
        pass

findings: list[tuple[str, str, str]] = []  # (shape, severity, message)


def note(shape: str, sev: str, msg: str) -> None:
    findings.append((shape, sev, msg))


# ---------------------------------------------------------------- S1
def s1_reader_without_writer() -> None:
    """Public functions defined in a module that nothing outside it ever calls.

    The hkjc_results_db defect was exactly this: `sync_meeting_results` did not
    exist and `get_*` had five callers, so the store looked alive from the read
    side. Here we look for the mirror image -- a write-shaped function that no
    caller anywhere invokes.
    """
    write_verbs = ("write", "save", "store", "sync", "record", "persist",
                   "ingest", "append", "flush", "mirror", "backfill")
    defined: dict[str, Path] = {}
    for p, tree in TREE.items():
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                if any(v in node.name.lower() for v in write_verbs):
                    defined.setdefault(node.name, p)
    called: set[str] = set()
    for p, tree in TREE.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                nm = getattr(f, "id", None) or getattr(f, "attr", None)
                if nm:
                    called.add(nm)
    # names referenced as bare attributes / strings count too (getattr, CLI maps)
    for p, s in SRC.items():
        for name in list(defined):
            if name in called:
                continue
            if re.search(rf'["\']{re.escape(name)}["\']', s):
                called.add(name)
    orphans = {n: p for n, p in defined.items() if n not in called}
    for name, p in sorted(orphans.items(), key=lambda kv: kv[0]):
        note("S1", "warn", f"寫入型 function 冇任何 caller：{name}()  @ {rel(p)}")
    if not orphans:
        note("S1", "ok", f"掃咗 {len(defined)} 個寫入型 public function，全部有 caller")


# ---------------------------------------------------------------- S2
def s2_hardcoded_engine_constants() -> None:
    """Literal lists/sets that duplicate a constant the engine owns."""
    eng = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/scoring.py"
    if not eng.exists():
        note("S2", "warn", "搵唔到 au_racing_engine/scoring.py，跳過")
        return
    etree = ast.parse(eng.read_text(encoding="utf-8"))
    owned: dict[str, set[str]] = {}
    for node in etree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if not isinstance(tgt, ast.Name) or not tgt.id.isupper():
                continue
            vals: set[str] = set()
            v = node.value
            if isinstance(v, (ast.List, ast.Tuple, ast.Set)):
                vals = {e.value for e in v.elts if isinstance(e, ast.Constant)
                        and isinstance(e.value, str)}
            elif isinstance(v, ast.Dict):
                vals = {k.value for k in v.keys if isinstance(k, ast.Constant)
                        and isinstance(k.value, str)}
            if len(vals) >= 4:
                owned[tgt.id] = vals

    for p, tree in TREE.items():
        if p == eng or "/tests/" in str(p):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            v = node.value
            lits: set[str] = set()
            if isinstance(v, (ast.List, ast.Tuple, ast.Set)):
                lits = {e.value for e in v.elts if isinstance(e, ast.Constant)
                        and isinstance(e.value, str)}
            elif isinstance(v, ast.Dict):
                lits = {k.value for k in v.keys if isinstance(k, ast.Constant)
                        and isinstance(k.value, str)}
            if len(lits) < 4:
                continue
            for cname, cvals in owned.items():
                inter = lits & cvals
                if len(inter) >= 4 and len(inter) >= 0.6 * len(lits):
                    tgt = node.targets[0]
                    tname = getattr(tgt, "id", "<expr>")
                    missing = cvals - lits
                    sev = "FAIL" if missing else "warn"
                    extra = f"，比引擎少咗 {sorted(missing)}" if missing else "（暫時同步）"
                    note("S2", sev,
                         f"{rel(p)}:{node.lineno} {tname} 硬抄咗 scoring.{cname} "
                         f"嘅 {len(inter)} 個值{extra}")


# ---------------------------------------------------------------- S3
def s3_exact_string_lookups() -> None:
    """Filename built from a date prefix, or membership tests on a name set."""
    pat_prefix = re.compile(r'f["\'][^"\']*\{\s*(date_prefix|prefix|date_str|day)\s*\}')
    pat_eqname = re.compile(r'\.name\s*==\s*["\']')
    for p, s in SRC.items():
        if "/tests/" in str(p):
            continue
        for i, line in enumerate(s.splitlines(), 1):
            if pat_prefix.search(line) and (".md" in line or ".json" in line or ".csv" in line):
                note("S3", "warn", f"{rel(p)}:{i} 用 date_prefix 砌檔名（兩邊都混用長短前綴）："
                                   f" {line.strip()[:80]}")
            if pat_eqname.search(line):
                note("S3", "warn", f"{rel(p)}:{i} 目錄／檔名精確比對：{line.strip()[:80]}")


# ---------------------------------------------------------------- S4
def s4_written_but_never_filled() -> None:
    """Keyword-only params that no call site ever passes."""
    interesting = re.compile(r"(speedmap|odds|sectional|geometry|run_style|"
                             r"trial|prize|going|barrier)", re.I)
    kwonly: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for p, tree in TREE.items():
        if "/tests/" in str(p):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = list(node.args.kwonlyargs) + list(node.args.args)
                for a in args:
                    if interesting.search(a.arg):
                        kwonly[a.arg].append((p, node.lineno))
    passed: set[str] = set()
    for p, tree in TREE.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg:
                        passed.add(kw.arg)
    for name, sites in sorted(kwonly.items()):
        if name in passed:
            continue
        head = sites[0]
        note("S4", "warn",
             f"參數 `{name}` 有 {len(sites)} 個定義位但冇一個 caller 用關鍵字傳過 "
             f"（例：{rel(head[0])}:{head[1]}）")


# ---------------------------------------------------------------- S5
def s5_one_way_guards() -> None:
    """Tests that assert subset in one direction only."""
    tests = [p for p in FILES if "/tests/" in str(p)]
    for p in tests:
        s = SRC[p]
        for m in re.finditer(r"def (test_\w+)\(.*?\n(.*?)(?=\ndef |\nclass |\Z)", s, re.S):
            name, body = m.group(1), m.group(2)
            subs = re.findall(r"issubset|<=|assertLessEqual", body)
            sups = re.findall(r"issuperset|>=|assertGreaterEqual|assertSetEqual|assertEqual", body)
            if subs and not sups and ("set(" in body or "SET" in body or "KEYS" in body
                                      or "FEATURES" in body):
                note("S5", "warn",
                     f"{rel(p)} :: {name} 只查一個方向（有 subset 冇 superset／equal）")


for fn in (s1_reader_without_writer, s2_hardcoded_engine_constants,
           s3_exact_string_lookups, s4_written_but_never_filled, s5_one_way_guards):
    fn()

TITLES = {
    "S1": "有 reader 冇 writer",
    "S2": "硬抄咗一份引擎常數",
    "S3": "精確字串比對／date_prefix 砌檔名",
    "S4": "欄位寫得出但永遠係空",
    "S5": "單向守衛",
}
print(f"掃咗 {len(FILES)} 個 AU／shared Python 檔\n")
for shape in ("S1", "S2", "S3", "S4", "S5"):
    rows = [f for f in findings if f[0] == shape]
    fails = [r for r in rows if r[1] == "FAIL"]
    print(f"── {shape} {TITLES[shape]} ── {len(rows)} 項"
          + (f"（{len(fails)} 個 FAIL）" if fails else ""))
    for _, sev, msg in rows[:25]:
        mark = {"FAIL": "❌", "warn": "⚠️ ", "ok": "✅"}[sev]
        print(f"  {mark} {msg}")
    if len(rows) > 25:
        print(f"  … 仲有 {len(rows) - 25} 項")
    print()
