#!/usr/bin/env python3
"""Wong Choi 異地加密備份（系統升級第 2 項，2026-11-25）。

點解：GitHub 只有 code。賽前快照、BSP 記錄、ROI 帳、網球帳全部只喺部 Mac 同屋企個外置碟，
屋企出事 = 全部冇咗，而且好多來源（Sportsbet 只留 ~11 日）冇得重抓。

做法：
  * 資料分「組」（頂層資料夾；大過 GROUP_SPLIT_BYTES 嘅再按子資料夾名頭 7 個字 —— 通常係 YYYY-MM —— 分）。
  * 每組 fingerprint = (相對路徑, 大細, mtime) 排序後 sha256。同上一代一樣就重用上一代嘅 object，唔重新上傳。
  * 變咗嘅組：tar → zstd → openssl AES-256-CBC（PBKDF2 20 萬次，鑰匙檔）→ 切 PART_BYTES 一舊 → 上傳。
  * 每代一份 manifest（記每組嘅 object、sha256、檔案清單），本身都加密上傳；保留最近 KEEP_GENERATIONS 代。
  * `drill` = 還原演練：隨機揀組，下載、核 sha256、解密、解壓，對返來源檔案大細同內容。

後端：`local:<資料夾>`（測試／第二隻碟）或 `r2:<bucket>`（Cloudflare R2，經 wrangler，用 dashboard 釘死嘅版本）。
設定：`~/.wongchoi_offsite.json` {"backend": "...", "key_file": "~/.wongchoi_offsite.key"}。
⚠️ 鑰匙一定要另外抄一份去密碼管理器 —— 部 Mac 冇咗而鑰匙得一份 = 個備份解唔返。

    python3 offsite_backup.py init --backend r2:wongchoi-offsite     # 開鑰匙＋設定（唔會自己開 bucket）
    python3 offsite_backup.py run [--dry-run]
    python3 offsite_backup.py drill [--groups 3]
    python3 offsite_backup.py restore --dest <空資料夾> [--group <組名>] [--generation G]   # 新機都用得：只要 backend＋鑰匙
    python3 offsite_backup.py status

安全（Sol 覆核 2026-11-25）：
  * 任何一個來源唔存在（例如外置碟冇插）→ 成次 run 停，唔寫新一代 —— 否則嗰啲組會喺新 manifest 消失，
    7 代之後佢哋嘅遠端副本就會被保留規則刪走。
  * `flock` 鎖：兩個 run 唔可以同時跑（同時清理會刪咗對方仲用緊嘅 object）。
  * 每代上傳 `manifests/LATEST`（明文代號），還原／演練由遠端讀，唔靠本機 state —— 部 Mac 冇咗都還原到。
  * 分段 sha256 記喺加密 manifest 入面，下載後先核對先解密（CBC 本身冇驗證，靠呢個）。
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import random
import secrets
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
REPO = Path(__file__).resolve().parents[2]
CONFIG = Path(os.environ.get("WC_OFFSITE_CONFIG", HOME / ".wongchoi_offsite.json"))
STATE = Path(os.environ.get("WC_OFFSITE_STATE",
                            HOME / "WongChoiData" / "WongChoiControl" / "offsite_backup_state.json"))
ARCHIVE = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive")
SCRATCH = ARCHIVE / "scratch" / "offsite-backup"
PART_BYTES = 200 * 1024 * 1024          # wrangler r2 object put 上限 ~300MB
GROUP_SPLIT_BYTES = 1024 ** 3
KEEP_GENERATIONS = 7
PBKDF2_ITER = 200_000
STALE_HOURS = 30                        # 健康檢查：超過呢個鐘數冇成功 = 警號

# (組名前綴, 來源)。外置碟獨有嘅嘢都要包：佢同部 Mac 喺同一間屋。
SOURCES = [
    ("data", HOME / "WongChoiData"),
    ("betfair-log", ARCHIVE / "betfair-market-log"),
    ("pred-snapshots", ARCHIVE / "prediction-snapshots"),
]
TENNIS_DB_POINTER = HOME / ".wongchoi_tennis_db"
SKIP_NAMES = {".DS_Store", "__pycache__", ".pytest_cache"}
SKIP_SUFFIXES = (".db-wal", ".db-shm", ".pyc", ".tmp")


class BackupError(RuntimeError):
    pass


# ---------------------------------------------------------------- 設定

def load_config() -> dict:
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackupError(f"未設定：{CONFIG}（先跑 init）") from exc
    cfg["key_file"] = str(Path(cfg.get("key_file") or HOME / ".wongchoi_offsite.key").expanduser())
    if not Path(cfg["key_file"]).exists():
        raise BackupError(f"鑰匙檔唔存在：{cfg['key_file']}")
    return cfg


def _write_private(path: Path, text: str) -> None:
    """一開始就係 0600（唔係先寫後改權限）。"""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, 0o600)


def cmd_init(backend: str, key_file: Path) -> dict:
    key_file = key_file.expanduser()
    backend_for(backend)                      # 唔識嘅 backend 即刻報錯
    if not key_file.exists():
        _write_private(key_file, secrets.token_urlsafe(48) + "\n")
        created = True
    else:
        created = False
    _write_private(CONFIG, json.dumps({"backend": backend, "key_file": str(key_file)}, indent=1))
    return {"config": str(CONFIG), "key_file": str(key_file), "key_created": created}


# ---------------------------------------------------------------- 後端

class LocalBackend:
    def __init__(self, root: str):
        self.root = Path(root).expanduser()

    def put(self, key: str, path: Path) -> None:
        dest = self.root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".partial")
        shutil.copyfile(path, tmp)
        tmp.replace(dest)

    def get(self, key: str, path: Path) -> None:
        src = self.root / key
        if not src.exists():
            raise BackupError(f"object 唔存在：{key}")
        shutil.copyfile(src, path)

    def delete(self, key: str) -> None:
        try:
            (self.root / key).unlink()
        except FileNotFoundError:
            pass


class R2Backend:
    """Cloudflare R2，經 wrangler（版本跟 Horse_Racing_Dashboard/package.json，同 deploy 一樣釘死）。"""

    def __init__(self, bucket: str):
        self.bucket = bucket
        pkg = json.loads((REPO / "Horse_Racing_Dashboard" / "package.json").read_text(encoding="utf-8"))
        self.version = pkg["devDependencies"]["wrangler"]

    def _run(self, *args: str) -> None:
        cmd = ["npx", "--yes", f"wrangler@{self.version}", "r2", "object", *args, "--remote"]
        for attempt in range(3):
            proc = subprocess.run(cmd, cwd=REPO / "Horse_Racing_Dashboard", capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=1800)
            if proc.returncode == 0:
                return
            time.sleep(5 * (attempt + 1))
        raise BackupError(f"wrangler {' '.join(args[:2])} 失敗：{(proc.stderr or proc.stdout)[-400:]}")

    def put(self, key: str, path: Path) -> None:
        self._run("put", f"{self.bucket}/{key}", "--file", str(path))

    def get(self, key: str, path: Path) -> None:
        self._run("get", f"{self.bucket}/{key}", "--file", str(path))

    def delete(self, key: str) -> None:
        self._run("delete", f"{self.bucket}/{key}")


def backend_for(spec: str):
    kind, _, arg = spec.partition(":")
    if kind == "local" and arg:
        return LocalBackend(arg)
    if kind == "r2" and arg:
        return R2Backend(arg)
    raise BackupError(f"唔識嘅 backend：{spec}（用 local:<路徑> 或者 r2:<bucket>）")


# ---------------------------------------------------------------- 分組

def _walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_NAMES)
        for name in sorted(filenames):
            if name in SKIP_NAMES or name.endswith(SKIP_SUFFIXES):
                continue
            p = Path(dirpath) / name
            if p.is_symlink() or not p.is_file():
                continue
            yield p


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in _walk(path))


def plan_groups(sources=None) -> list[dict]:
    """→ [{"name", "base", "members": [相對 base 嘅路徑]}]。"""
    groups = []
    for prefix, root in (SOURCES if sources is None else sources):
        if not root.exists():
            continue
        for entry in sorted(root.iterdir()):
            if entry.name in SKIP_NAMES or entry.is_symlink():
                continue
            if entry.is_dir() and _size(entry) > GROUP_SPLIT_BYTES:
                buckets: dict[str, list[str]] = {}
                for child in sorted(entry.iterdir()):
                    if child.name in SKIP_NAMES or child.is_symlink():
                        continue
                    buckets.setdefault(child.name[:7], []).append(f"{entry.name}/{child.name}")
                for tag, members in buckets.items():
                    groups.append({"name": _safe(f"{prefix}/{entry.name}/{tag}"), "base": str(root), "members": members})
            else:
                groups.append({"name": _safe(f"{prefix}/{entry.name}"), "base": str(root), "members": [entry.name]})
    return groups


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_./" else "_" for c in name)


def file_list(group: dict) -> list[list]:
    base = Path(group["base"])
    out = []
    for m in group["members"]:
        p = base / m
        files = [p] if p.is_file() else list(_walk(p))
        for f in files:
            st = f.stat()
            out.append([f.relative_to(base).as_posix(), st.st_size, st.st_mtime_ns])
    return sorted(out)


def fingerprint(files: list[list]) -> str:
    return hashlib.sha256(json.dumps(files, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------- 加密打包

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pack(group: dict, files: list[list], key_file: str, workdir: Path) -> list[Path]:
    """tar（只包 file_list 列出嘅檔）→ zstd → openssl → 切舊。→ 每舊嘅路徑。"""
    listing = workdir / "files.txt"
    listing.write_bytes(b"".join(f[0].encode("utf-8") + b"\0" for f in files))   # NUL 分隔：檔名有換行都唔會錯
    prefix = workdir / "part."
    pipeline = (
        f"tar -C {shlex.quote(group['base'])} --null -cf - -T {shlex.quote(str(listing))}"
        f" | zstd -q -T0 -10"
        f" | openssl enc -aes-256-cbc -pbkdf2 -iter {PBKDF2_ITER} -salt -pass file:{shlex.quote(key_file)}"
        f" | split -b {PART_BYTES} -a 3 - {shlex.quote(str(prefix))}"
    )
    proc = subprocess.run(["/bin/bash", "-o", "pipefail", "-c", pipeline], capture_output=True,
                          encoding="utf-8", errors="replace")
    listing.unlink()
    if proc.returncode != 0:
        raise BackupError(f"打包 {group['name']} 失敗：{proc.stderr[-400:]}")
    return sorted(workdir.glob("part.*"))


def unpack(parts: list[Path], key_file: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    cat = " ".join(shlex.quote(str(p)) for p in parts)
    pipeline = (f"cat {cat} | openssl enc -d -aes-256-cbc -pbkdf2 -iter {PBKDF2_ITER} -pass file:{shlex.quote(key_file)}"
                f" | zstd -q -d | tar -C {shlex.quote(str(dest))} -xf -")
    proc = subprocess.run(["/bin/bash", "-o", "pipefail", "-c", pipeline], capture_output=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise BackupError(f"解包失敗：{proc.stderr[-400:]}")


def _encrypt_json(obj: dict, key_file: str, path: Path) -> None:
    raw = json.dumps(obj, ensure_ascii=False).encode()
    proc = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", str(PBKDF2_ITER), "-salt",
                           "-pass", f"file:{key_file}", "-out", str(path)], input=raw, capture_output=True)
    if proc.returncode != 0:
        raise BackupError("manifest 加密失敗")


def _decrypt_json(path: Path, key_file: str) -> dict:
    proc = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", str(PBKDF2_ITER),
                           "-pass", f"file:{key_file}", "-in", str(path)], capture_output=True)
    if proc.returncode != 0:
        raise BackupError("manifest 解唔到（鑰匙錯？）")
    return json.loads(proc.stdout)


# ---------------------------------------------------------------- 狀態

def read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def _workroot() -> Path:
    """暫存：外置碟有掛載就用（AGENTS.md：>1GB 暫存放外置碟），冇就用系統 tmp（每組做完即刪，最多一組大）。"""
    if os.path.ismount("/Volumes/Kelvin Hardisk 1"):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        return SCRATCH
    return Path(tempfile.gettempdir())


def _tennis_snapshot(workdir: Path) -> Path | None:
    """網球 DB 每日寫緊：用 sqlite backup API 攞一致快照，唔直接抄（會抄到寫一半）。"""
    try:
        db = Path(TENNIS_DB_POINTER.read_text(encoding="utf-8").strip())
    except OSError:
        return None
    if not db.exists():
        return None
    out = workdir / "tennis-db"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "tennis_wc.db"
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return out


# ---------------------------------------------------------------- run

def _lock():
    path = STATE.with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        fh.close()
        raise BackupError("另一個異地備份 run 進行緊") from exc
    return fh


def cmd_run(dry_run: bool = False, cfg: dict | None = None, sources=None) -> dict:
    cfg = cfg or load_config()
    be = backend_for(cfg["backend"])
    lock = _lock()
    try:
        return _run_locked(dry_run, cfg, be, sources)
    finally:
        lock.close()


def _run_locked(dry_run, cfg, be, sources):
    state = read_state()
    prev = {g["name"]: g for g in (state.get("last_manifest_groups") or [])}
    gen = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)   # 同一秒兩次唔撞名
    work = Path(tempfile.mkdtemp(prefix="offsite-", dir=_workroot()))
    srcs = list(SOURCES if sources is None else sources)
    try:
        tdb = _tennis_snapshot(work) if sources is None else None
        if tdb:
            srcs.append(("tennis", tdb.parent))
        # 來源唔喺度（外置碟冇插／網球 DB 讀唔到）→ 上一代嗰啲組原封不動帶落新一代。
        # 唔帶嘅話佢哋會喺新 manifest 消失，7 代之後遠端副本就俾保留規則刪走（Sol 覆核 2026-11-25）。
        absent = {prefix for prefix, root in srcs if not root.exists()}
        if sources is None and not tdb:
            absent.add("tennis")
        carried = []
        if absent and state.get("generations") and not dry_run:
            _, prev_manifest = _remote_manifest(be, cfg, work)
            carried = [g for g in prev_manifest["groups"] if g["name"].split("/", 1)[0] in absent]
        groups = plan_groups([(p, r) for p, r in srcs if r.exists()])
        if tdb:
            # 快照每次都係新 mtime：fingerprint 用內容 hash，唔係 mtime
            for g in groups:
                if g["name"].startswith("tennis/"):
                    g["content_hash"] = _sha256(tdb / "tennis_wc.db")
        manifest = {"generation": gen, "created_at": datetime.now(timezone.utc).isoformat(), "groups": []}
        uploaded = reused = up_bytes = 0
        for g in groups:
            files = file_list(g)
            fp = g.get("content_hash") or fingerprint(files)
            old = prev.get(g["name"])
            entry = {"name": g["name"], "fingerprint": fp, "files": files}
            if old and old.get("fingerprint") == fp:
                entry["objects"] = old["objects"]
                reused += 1
            elif dry_run:
                entry["objects"] = []
                uploaded += 1
            else:
                gdir = work / "g"
                gdir.mkdir()
                parts = pack(g, files, cfg["key_file"], gdir)
                objs = []
                for i, p in enumerate(parts):
                    key = f"objects/{g['name']}/{gen}.{i:03d}"
                    be.put(key, p)
                    objs.append({"key": key, "sha256": _sha256(p), "bytes": p.stat().st_size})
                    up_bytes += p.stat().st_size
                shutil.rmtree(gdir)
                entry["objects"] = objs
                uploaded += 1
            manifest["groups"].append(entry)
        manifest["groups"].extend(carried)
        summary = {"generation": gen, "groups": len(groups) + len(carried), "uploaded_groups": uploaded,
                   "reused_groups": reused, "carried_groups": len(carried), "absent_sources": sorted(absent),
                   "uploaded_bytes": up_bytes,
                   "files": sum(len(g["files"]) for g in manifest["groups"])}
        if dry_run:
            return summary | {"dry_run": True}
        mpath = work / "manifest.enc"
        _encrypt_json(manifest, cfg["key_file"], mpath)
        be.put(f"manifests/{gen}.enc", mpath)
        latest = work / "LATEST"
        latest.write_text(gen + "\n", encoding="utf-8")
        be.put("manifests/LATEST", latest)
        gens = (state.get("generations") or []) + [gen]
        # 保留最近幾代；其餘 manifest 同冇被保留代引用嘅 object 刪走
        keep, drop = gens[-KEEP_GENERATIONS:], gens[:-KEEP_GENERATIONS]
        gen_objects = dict(state.get("gen_objects") or {})
        gen_objects[gen] = sorted({o["key"] for g in manifest["groups"] for o in g["objects"]})
        gen_objects = {k: v for k, v in gen_objects.items() if k in keep}
        live = {key for keys in gen_objects.values() for key in keys}
        for old_gen in drop:
            be.delete(f"manifests/{old_gen}.enc")
        for key in sorted(set(state.get("all_objects") or []) - live):   # 冇保留代引用 = 刪
            be.delete(key)
        state.update({
            "backend": cfg["backend"], "generations": keep, "last_success": manifest["created_at"],
            "last_summary": summary,
            "last_manifest_groups": [{k: v for k, v in g.items() if k != "files"} for g in manifest["groups"]],
            "gen_objects": gen_objects, "all_objects": sorted(live),
        })
        write_state(state)
        return summary
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- drill

def cmd_drill(n_groups: int = 3, cfg: dict | None = None, seed: int | None = None, sources=None) -> dict:
    """還原演練：攞最新 manifest，隨機 n 組下載、核 sha256、解密解壓，同來源比對（冇郁過嘅檔要內容一樣）。"""
    cfg = cfg or load_config()
    be = backend_for(cfg["backend"])
    state = read_state()
    work = Path(tempfile.mkdtemp(prefix="offsite-drill-", dir=_workroot()))
    try:
        gen, manifest = _remote_manifest(be, cfg, work)
        rng = random.Random(seed)
        groups = [g for g in manifest["groups"] if g["objects"]]
        if not groups:
            raise BackupError("最新一代冇任何組可以還原")
        picked = rng.sample(groups, min(n_groups, len(groups)))
        base_of = {g["name"]: g["base"] for g in plan_groups(SOURCES if sources is None else sources)}
        results = []
        for g in picked:
            gdir = work / "dl"
            gdir.mkdir()
            parts = []
            for i, o in enumerate(g["objects"]):
                p = gdir / f"part.{i:03d}"
                be.get(o["key"], p)
                if _sha256(p) != o["sha256"]:
                    raise BackupError(f"{o['key']} sha256 對唔上")
                parts.append(p)
            out = work / "restore"
            unpack(parts, cfg["key_file"], out)
            restored = {f.relative_to(out).as_posix(): f for f in _walk(out)}
            missing = [f[0] for f in g["files"] if f[0] not in restored]
            size_bad = [f[0] for f in g["files"] if f[0] in restored and restored[f[0]].stat().st_size != f[1]]
            # 內容抽查：來源冇郁過（大細＋mtime 一樣）嘅檔，逐 byte hash 比較（最多 50 個）
            base = base_of.get(g["name"])
            checked = content_bad = 0
            if base:
                for rel, size, mtime in rng.sample(g["files"], min(50, len(g["files"]))):
                    src = Path(base) / rel
                    try:
                        st = src.stat()
                    except OSError:
                        continue
                    if st.st_size == size and st.st_mtime_ns == mtime and rel in restored:
                        checked += 1
                        content_bad += _sha256(src) != _sha256(restored[rel])
            results.append({"group": g["name"], "files": len(g["files"]), "missing": len(missing),
                            "size_mismatch": len(size_bad), "content_checked": checked,
                            "content_mismatch": content_bad})
            shutil.rmtree(gdir)
            shutil.rmtree(out)
        ok = bool(results) and all(r["missing"] == 0 and r["size_mismatch"] == 0 and r["content_mismatch"] == 0
                                   for r in results)
        report = {"generation": gen, "ok": ok, "groups": results, "at": datetime.now(timezone.utc).isoformat()}
        state["last_drill"] = report
        write_state(state)
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _remote_manifest(be, cfg, work: Path, generation: str | None = None) -> tuple[str, dict]:
    """由遠端讀（唔靠本機 state）：LATEST → manifest。"""
    if generation is None:
        p = work / "LATEST"
        be.get("manifests/LATEST", p)
        generation = p.read_text(encoding="utf-8").strip()
    mpath = work / "manifest.enc"
    be.get(f"manifests/{generation}.enc", mpath)
    return generation, _decrypt_json(mpath, cfg["key_file"])


def cmd_restore(dest: Path, group: str | None = None, generation: str | None = None,
                cfg: dict | None = None) -> dict:
    """還原去一個空資料夾（新機都用得：只需要 config／鑰匙同 backend）。唔會覆蓋現有資料。"""
    cfg = cfg or load_config()
    be = backend_for(cfg["backend"])
    dest = dest.expanduser()
    if dest.exists() and any(dest.iterdir()):
        raise BackupError(f"{dest} 唔係空資料夾 —— 還原唔會覆蓋現有檔案")
    work = Path(tempfile.mkdtemp(prefix="offsite-restore-", dir=_workroot()))
    try:
        gen, manifest = _remote_manifest(be, cfg, work, generation)
        groups = [g for g in manifest["groups"] if g["objects"] and (group is None or g["name"] == group)]
        if not groups:
            raise BackupError(f"冇組可以還原（group={group}）")
        files = 0
        for g in groups:
            gdir = work / "dl"
            gdir.mkdir()
            parts = []
            for i, o in enumerate(g["objects"]):
                p = gdir / f"part.{i:03d}"
                be.get(o["key"], p)
                if _sha256(p) != o["sha256"]:
                    raise BackupError(f"{o['key']} sha256 對唔上")
                parts.append(p)
            prefix = g["name"].split("/", 1)[0]
            unpack(parts, cfg["key_file"], dest / prefix)
            files += len(g["files"])
            shutil.rmtree(gdir)
        return {"generation": gen, "groups": len(groups), "files": files, "dest": str(dest)}
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- status

def status(now: datetime | None = None) -> dict:
    """健康檢查用：configured／fresh／drill。"""
    now = now or datetime.now(timezone.utc)
    state = read_state()
    out = {"configured": CONFIG.exists(), "backend": state.get("backend"),
           "last_success": state.get("last_success"), "generations": len(state.get("generations") or []),
           "last_drill_ok": (state.get("last_drill") or {}).get("ok"),
           "last_drill_at": (state.get("last_drill") or {}).get("at")}
    if out["last_success"]:
        age = (now - datetime.fromisoformat(out["last_success"])).total_seconds() / 3600
        out["age_hours"] = round(age, 1)
        out["fresh"] = age <= STALE_HOURS
    else:
        out["fresh"] = False
    return out


def _notify(msg: str) -> None:
    try:
        sys.path.insert(0, str(REPO / ".agents" / "skills" / "shared_racing" / "scripts"))
        import racing_telegram
        racing_telegram.send_message(msg, audience="primary")
    except Exception as exc:  # noqa: BLE001
        print(f"Telegram 推送失敗：{type(exc).__name__}", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--backend", required=True)
    i.add_argument("--key-file", default=str(HOME / ".wongchoi_offsite.key"))
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--notify", action="store_true", help="失敗推 Telegram（排程用）")
    d = sub.add_parser("drill")
    d.add_argument("--groups", type=int, default=3)
    d.add_argument("--notify", action="store_true")
    rs = sub.add_parser("restore")
    rs.add_argument("--dest", required=True)
    rs.add_argument("--group")
    rs.add_argument("--generation")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "init":
            res = cmd_init(a.backend, Path(a.key_file))
            print(json.dumps(res, ensure_ascii=False, indent=1))
            if res["key_created"]:
                print("⚠️ 即刻將鑰匙檔內容抄去密碼管理器 —— 部 Mac 冇咗就靠佢解密。")
        elif a.cmd == "run":
            print(json.dumps(cmd_run(a.dry_run), ensure_ascii=False, indent=1))
        elif a.cmd == "drill":
            rep = cmd_drill(a.groups)
            print(json.dumps(rep, ensure_ascii=False, indent=1))
            if not rep["ok"]:
                if a.notify:
                    _notify(f"⚠️ 異地備份還原演練失敗（{rep['generation']}）：{rep['groups']}")
                return 1
        elif a.cmd == "restore":
            print(json.dumps(cmd_restore(Path(a.dest), a.group, a.generation), ensure_ascii=False, indent=1))
        else:
            print(json.dumps(status(), ensure_ascii=False, indent=1))
    except BackupError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        if getattr(a, "notify", False):
            _notify(f"⚠️ 異地備份 {a.cmd} 失敗：{exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
