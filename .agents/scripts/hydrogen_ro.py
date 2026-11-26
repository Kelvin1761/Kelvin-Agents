#!/usr/bin/env python3
"""Hydrogen（agy headless）唯一准行嘅命令：純 Python 唯讀搜尋（Kelvin 2026-11-26；Sol 覆核要求）。

點解唔直接批 rg／git：`rg --pre` 會開子程序、`git diff/log --output` 會寫檔、絕對路徑可以讀 workspace 外嘅秘密檔。
而且 agy 沙箱入面 wrapper 開唔到子程序（2026-11-26 實測 rg EPERM），所以全部用 Python 自己做，唔 exec 任何嘢。
所有路徑 resolve 之後一定要喺 WC_HYDROGEN_ROOTS（codex_delegate 設：--cd、brief 資料夾、--add-dir）入面；
唔跟 symlink；參數唔准以 `-` 開頭；輸出截斷到 MAX_OUT 字。

    hydrogen_ro.py grep <regex> [路徑…]     # 逐行搜尋，印 檔:行:內容（最多 MAX_HITS 行）
    hydrogen_ro.py ls [路徑]                 # 列資料夾
    hydrogen_ro.py wc <路徑…>                # 行數同字節
"""
from __future__ import annotations

import os
import re
import resource
import stat
import sys
from pathlib import Path

MAX_OUT = 60_000
MAX_HITS = 300
MAX_FILE = 5 * 1024 * 1024
MAX_PATTERN = 200
TIME_LIMIT = 30  # 秒：regex 拖死／超大目錄都會被切
# codex_delegate 每次 run 會將呢個檔抄去 workspace 以外嘅暫存資料夾，並將允許路徑寫死入呢行（環境變數改唔到）
EMBEDDED_ROOTS: list[str] = []
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}


class Refused(Exception):
    pass


def roots() -> list[Path]:
    raw = EMBEDDED_ROOTS or os.environ.get("WC_HYDROGEN_ROOTS", "").split(os.pathsep)
    out = [Path(p).resolve() for p in raw if p.strip()]
    if not out:
        raise Refused("WC_HYDROGEN_ROOTS 冇設（只可以由 codex_delegate 叫）")
    return out


def inside(path: Path, allowed: list[Path]) -> bool:
    return any(path == r or r in path.parents for r in allowed)


def safe_path(arg: str, allowed: list[Path]) -> Path:
    if arg.startswith("-"):
        raise Refused(f"參數唔准以 - 開頭：{arg}")
    p = Path(arg)
    resolved = (p if p.is_absolute() else Path.cwd() / p).resolve()
    if not inside(resolved, allowed):
        raise Refused(f"路徑唔喺 workspace 入面：{arg}")
    return resolved


def iter_files(base: Path, allowed: list[Path]):
    if base.is_file():
        yield base
        return
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            f = Path(dirpath) / name
            if f.is_symlink() or not inside(f.resolve(), allowed):
                continue
            yield f


def read_regular(f: Path) -> bytes | None:
    """開檔先驗（唔跟 symlink、唔等 FIFO），用 fd 驗普通檔同大細，最多讀 MAX_FILE：冇 stat→open 競態。"""
    try:
        fd = os.open(f, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE:
            return None
        chunks, total = [], 0
        while total <= MAX_FILE:
            b = os.read(fd, min(1 << 20, MAX_FILE + 1 - total))
            if not b:
                break
            chunks.append(b)
            total += len(b)
        return None if total > MAX_FILE else b"".join(chunks)
    finally:
        os.close(fd)


def cmd_grep(args: list[str], allowed: list[Path]) -> str:
    if not args:
        raise Refused("grep 要 pattern")
    if len(args[0]) > MAX_PATTERN:
        raise Refused(f"pattern 太長（> {MAX_PATTERN} 字）")
    try:
        rx = re.compile(args[0])
    except re.error as exc:
        raise Refused(f"regex 唔啱：{exc}")
    bases = [safe_path(a, allowed) for a in args[1:]] or [safe_path(".", allowed)]
    cwd = Path.cwd().resolve()
    out, hits = [], 0
    for base in bases:
        for f in iter_files(base, allowed):
            data = read_regular(f)
            if data is None:
                continue
            if b"\0" in data[:4096]:
                continue  # binary
            for i, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
                if rx.search(line):
                    shown = f.relative_to(cwd) if cwd in f.parents else f
                    out.append(f"{shown}:{i}:{line[:300]}")
                    hits += 1
                    if hits >= MAX_HITS:
                        out.append(f"…（夠 {MAX_HITS} 行，收窄搜尋）")
                        return "\n".join(out)
    return "\n".join(out) if out else "（冇結果）"


def cmd_ls(args: list[str], allowed: list[Path]) -> str:
    if len(args) > 1:
        raise Refused("ls 最多一個路徑")
    base = safe_path(args[0] if args else ".", allowed)
    if base.is_file():
        return f"{base.stat().st_size:>10}  {base.name}"
    rows = []
    for e in sorted(base.iterdir()):
        kind = "@" if e.is_symlink() else ("/" if e.is_dir() else "")
        size = e.lstat().st_size
        rows.append(f"{size:>10}  {e.name}{kind}")
    return "\n".join(rows) or "（空）"


def cmd_wc(args: list[str], allowed: list[Path]) -> str:
    if not args:
        raise Refused("wc 要路徑")
    rows = []
    for a in args:
        f = safe_path(a, allowed)
        data = read_regular(f)
        if data is None:
            raise Refused(f"唔係普通檔案、係 symlink 或者大過 {MAX_FILE // 1024 // 1024}MB：{a}")
        lines = data.count(b"\n")
        rows.append(f"{lines:>8} 行 {len(data):>10} bytes  {a}")
    return "\n".join(rows)


COMMANDS = {"grep": cmd_grep, "ls": cmd_ls, "wc": cmd_wc}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if __name__ == "__main__":  # CPU 上限由 kernel 執行：regex 卡喺 C 入面都會被殺（SIGALRM 做唔到）
        resource.setrlimit(resource.RLIMIT_CPU, (TIME_LIMIT, TIME_LIMIT + 1))
    try:
        if not argv or argv[0] not in COMMANDS:
            raise Refused(f"只准：{'、'.join(COMMANDS)}")
        out = COMMANDS[argv[0]](argv[1:], roots())
    except Refused as exc:
        print(f"⛔ {exc}", file=sys.stderr)
        return 2
    if len(out) > MAX_OUT:
        out = out[:MAX_OUT] + f"\n…（截斷，總共 {len(out)} 字；收窄搜尋）"
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
