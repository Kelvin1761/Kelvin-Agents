"""Read-only hot/warm/cold storage inventory for Central Wong Choi."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


GIB = 1024 ** 3
HOT_WARNING_FREE_BYTES = 30 * GIB
HOT_CRITICAL_FREE_BYTES = 20 * GIB
DEFAULT_HOT_ROOT = Path.home() / "WongChoiData"
DEFAULT_WARM_ROOT = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive")


def _configured_path(name: str, default: Path | None = None) -> Path | None:
    value = os.environ.get(name, "").strip()
    if value:
        return Path(value).expanduser()
    return default


def _mount_root(path: Path) -> Path:
    parts = path.parts
    if len(parts) >= 3 and parts[1] == "Volumes":
        return Path("/Volumes") / parts[2]
    return path


def _probe(path: Path) -> tuple[bool, str | None]:
    target = _mount_root(path)
    try:
        if not target.is_dir():
            return False, "not_mounted" if target.parent == Path("/Volumes") else "missing"
        next(target.iterdir(), None)
    except PermissionError:
        return False, "permission_denied"
    except OSError as exc:
        return False, f"{type(exc).__name__}:{exc}"
    return True, None


def _disk(path: Path) -> dict[str, Any]:
    target = path
    while not target.exists() and target != target.parent:
        target = target.parent
    try:
        stats = os.statvfs(target)
    except OSError as exc:
        return {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
    total = stats.f_frsize * stats.f_blocks
    free = stats.f_frsize * stats.f_bavail
    return {
        "status": "available",
        "total_bytes": total,
        "free_bytes": free,
        "free_gib": round(free / GIB, 2),
        "free_ratio": round(free / total, 4) if total else None,
    }


def _tree_size(path: Path) -> int | None:
    if not path.exists():
        return None
    total = 0
    try:
        for root, _, files in os.walk(path):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    continue
    except OSError:
        return None
    return total


def _tier(role: str, path: Path | None, *, required: bool) -> dict[str, Any]:
    if path is None:
        return {
            "role": role,
            "configured": False,
            "required": required,
            "status": "unconfigured",
        }
    accessible, error = _probe(path)
    result = {
        "role": role,
        "configured": True,
        "required": required,
        "path": str(path),
        "mount_root": str(_mount_root(path)),
        "status": "available" if accessible else "unavailable",
    }
    if error:
        result["error"] = error
    if accessible:
        result["disk"] = _disk(path)
    return result


def collect_storage_status(
    repo_root: Path,
    state_root: Path,
    *,
    scan: bool = False,
) -> dict[str, Any]:
    """Describe storage without moving, deleting or hydrating any artifact."""
    repo_root = repo_root.expanduser().resolve()
    inventory_repo = Path(
        os.environ.get("WC_RESEARCH_REPO_ROOT", str(repo_root))
    ).expanduser().resolve()
    state_root = state_root.expanduser().resolve()
    hot_root = _configured_path("WC_HOT_DATA_ROOT", DEFAULT_HOT_ROOT)
    warm_root = _configured_path("WC_WARM_ARCHIVE_ROOT", DEFAULT_WARM_ROOT)
    cold_root = _configured_path("WC_COLD_MIRROR_ROOT")

    hot = _tier("hot", hot_root, required=True)
    warm = _tier("warm", warm_root, required=True)
    cold = _tier("cold", cold_root, required=False)
    hot_disk = hot.get("disk") or {}
    free = hot_disk.get("free_bytes")
    if not isinstance(free, int):
        pressure = "unknown"
    elif free < HOT_CRITICAL_FREE_BYTES:
        pressure = "critical"
    elif free < HOT_WARNING_FREE_BYTES:
        pressure = "warning"
    else:
        pressure = "ok"
    hot["pressure"] = pressure
    hot["warning_free_gib"] = HOT_WARNING_FREE_BYTES // GIB
    hot["critical_free_gib"] = HOT_CRITICAL_FREE_BYTES // GIB

    inventory: list[dict[str, Any]] = []
    if scan:
        known = (
            ("repo", inventory_repo),
            ("control_state", state_root),
            ("tennis_live_db", inventory_repo / "tennis-wong-choi" / "tennis_wc.db"),
            ("tennis_db_backups", inventory_repo / "tennis-wong-choi" / "data" / "backups"),
            ("repo_scratch", inventory_repo / "scratch"),
            ("au_archive", (hot_root or DEFAULT_HOT_ROOT) / "Wong Choi Horse Race Analysis" / "AU_Racing" / "Archive"),
            ("hkjc_archive", (hot_root or DEFAULT_HOT_ROOT) / "Wong Choi Horse Race Analysis" / "HK_Racing"),
        )
        for name, path in known:
            size = _tree_size(path)
            inventory.append(
                {
                    "name": name,
                    "path": str(path),
                    "bytes": size,
                    "gib": round(size / GIB, 3) if isinstance(size, int) else None,
                }
            )
        inventory.sort(key=lambda item: item.get("bytes") or 0, reverse=True)

    attention: list[str] = []
    if pressure != "ok":
        attention.append(f"hot_storage_{pressure}")
    if warm["status"] != "available":
        attention.append("warm_archive_unavailable")
    if cold["configured"] and cold["status"] != "available":
        attention.append("cold_mirror_unavailable")
    return {
        "schema_version": "wong-choi-storage-status/v1",
        "status": "attention" if attention else "ok",
        "attention": attention,
        "tiers": {"hot": hot, "warm": warm, "cold": cold},
        "inventory": inventory,
        "inventory_repo": str(inventory_repo),
        "policy": {
            "hot": "live runs, current models, mutable databases and recent evidence",
            "warm": "settled raw archives, database snapshots and reproducible experiment artifacts",
            "cold": "second verified copy for disaster recovery; never a live database",
            "migration_gate": "copy -> hash manifest -> restore drill -> second copy -> approved source removal",
        },
    }


def render_storage_telegram(payload: dict[str, Any]) -> str:
    tiers = payload.get("tiers") or {}
    hot = tiers.get("hot") or {}
    warm = tiers.get("warm") or {}
    cold = tiers.get("cold") or {}
    hot_disk = hot.get("disk") or {}
    lines = [
        f"💾 Wong Choi Storage：{payload.get('status')}",
        f"HOT SSD：{hot.get('pressure')} · free {hot_disk.get('free_gib', 'N/A')} GiB",
        f"WARM 外置碟：{warm.get('status')} · {warm.get('path', '未設定')}",
        f"COLD Drive：{cold.get('status')} · {cold.get('path', '未設定')}",
    ]
    if payload.get("attention"):
        lines.append("留意：" + "、".join(payload["attention"]))
    lines.append("搬檔閘：copy → hash → restore → second copy → 批准後才刪本機")
    return "\n".join(lines)
