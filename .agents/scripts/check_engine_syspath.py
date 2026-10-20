#!/usr/bin/env python3
"""Fail if any code puts an engine *package directory* itself on sys.path.

AGENTS.md「五件唔可以做嘅事」#3. The engines are packages (`au_racing_engine`,
`hkjc_racing_engine`). Putting the package directory itself on `sys.path` turns
its modules back into top-level ones, so `scoring` / `engine_core` collide
again. The correct entry is the directory that *contains* the package.

This has bitten three times (PF token silently dead, 900e49c1 breaking five
entry points, the package rename taking production down overnight). grep cannot
catch it: the path is built over several lines and through a variable
(`_ENGINE = Path(__file__)... / "hkjc_racing_engine"`, then
`sys.path.insert(0, str(_ENGINE))`), so this walks the AST and resolves the
path expression statically.

    python3 .agents/scripts/check_engine_syspath.py [paths...]

Exit 0 = clean, 1 = violation (each line says file:line and how to fix it).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ENGINE_PACKAGES = {"au_racing_engine", "hkjc_racing_engine", "racing_engine"}
# scratch/ = one-off experiments, 9 of them still use the pre-rename `racing_engine`
# and are already dead by the rename; they never run in production.
SKIP_PARTS = {".git", ".agents/archive", "node_modules", ".venv", "__pycache__", "scratch/", "docs/experiments/"}
UNKNOWN = "?"


def _segments(node: ast.AST, env: dict[str, list[str]]) -> list[str] | None:
    """Best-effort static value of a path expression as a segment list."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [p for p in node.value.replace("\\", "/").split("/") if p]
    if isinstance(node, ast.Name):
        return list(env[node.id]) if node.id in env else [UNKNOWN]
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
        left = _segments(node.left, env)
        right = _segments(node.right, env)
        if left is None:
            return None
        return left + (right if right is not None else [UNKNOWN])
    if isinstance(node, ast.Attribute):
        base = _segments(node.value, env)
        if base is None:
            return None
        if node.attr == "parent":
            return base[:-1] if base else base
        return base  # .resolve / .absolute etc. keep the value
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) \
            and node.value.attr == "parents":
        base = _segments(node.value.value, env)
        idx = node.slice
        if base is not None and isinstance(idx, ast.Constant) and isinstance(idx.value, int):
            return base[: max(len(base) - (idx.value + 1), 0)]
        return None
    if isinstance(node, ast.Call):
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
        if name in {"str", "Path", "resolve", "absolute", "abspath", "realpath", "fspath"} and node.args:
            return _segments(node.args[0], env)
        if name == "join" and node.args:
            out: list[str] = []
            for arg in node.args:
                seg = _segments(arg, env)
                out += seg if seg is not None else [UNKNOWN]
            return out
        if isinstance(fn, ast.Attribute) and name in {"resolve", "absolute"}:
            return _segments(fn.value, env)
    return None


def _is_syspath_mutation(call: ast.Call) -> bool:
    fn = call.func
    if not (isinstance(fn, ast.Attribute) and fn.attr in {"insert", "append"}):
        return False
    target = fn.value
    return (isinstance(target, ast.Attribute) and target.attr == "path"
            and isinstance(target.value, ast.Name) and target.value.id == "sys")


def check_source(source: str, filename: str = "<src>") -> list[str]:
    try:
        tree = ast.parse(source, filename)
    except SyntaxError:
        return []
    env: dict[str, list[str]] = {}
    for node in ast.walk(tree):  # one hop is enough for the shapes seen so far
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            seg = _segments(node.value, env)
            if seg is not None:
                env[node.targets[0].id] = seg
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_syspath_mutation(node) and node.args:
            seg = _segments(node.args[-1], env)
            if seg and seg[-1] in ENGINE_PACKAGES:
                problems.append(
                    f"{filename}:{node.lineno}: sys.path 插咗 package 目錄本身 "
                    f"({seg[-1]})。改插佢上一層 (`.../scripts`)，"
                    f"然後 `from {seg[-1]}.scoring import ...`。見 AGENTS.md 五件事 #3。")
    return problems


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[2]
    targets = [Path(a) for a in argv] or [root]
    files: list[Path] = []
    for t in targets:
        files += [t] if t.is_file() else sorted(t.rglob("*.py"))
    problems: list[str] = []
    for f in files:
        rel = f.as_posix()
        if any(part in rel for part in SKIP_PARTS):
            continue
        try:
            problems += check_source(f.read_text(encoding="utf-8"), str(f.relative_to(root)) if f.is_relative_to(root) else str(f))
        except (OSError, UnicodeDecodeError):
            continue
    for p in problems:
        print("❌", p)
    if problems:
        print(f"\n{len(problems)} 處把引擎 package 目錄放上 sys.path。")
        return 1
    print(f"✅ 掃咗 {len(files)} 個 .py，冇引擎 package 目錄喺 sys.path。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
