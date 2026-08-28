"""Read-only hot/warm/cold storage inventory for Central Wong Choi."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .dashboard_backup import collect_d1_backup_status


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
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
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


def _catalog_cold_coverage(state_root: Path) -> dict[str, Any]:
    """Summarise point-in-time COLD proofs for every catalogued artifact."""
    catalog = state_root / "storage" / "catalog"
    records_dir = catalog / "records"
    events_dir = catalog / "events"
    if not records_dir.is_dir():
        return {
            "status": "no_data",
            "known_artifacts": 0,
            "verified_artifacts": 0,
            "unverified_artifacts": 0,
            "providers": [],
            "domains": {},
            "artifacts": [],
        }

    records: dict[str, dict[str, Any]] = {}
    invalid_records: list[str] = []
    for path in sorted(records_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            invalid_records.append(str(path))
            continue
        artifact_id = str(payload.get("artifact_id") or "")
        if payload.get("schema_version") != "wong-choi-artifact/v1" or not artifact_id:
            continue
        records[artifact_id] = payload

    proofs: dict[str, dict[str, Any]] = {}
    if events_dir.is_dir():
        for path in sorted(events_dir.glob("*.json")):
            try:
                event = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            artifact_id = str(event.get("artifact_id") or "")
            record = records.get(artifact_id)
            if not record or event.get("digest") != record.get("destination_digest"):
                continue
            schema = event.get("schema_version")
            if (
                schema == "wong-choi-artifact-remote-mirror/v1"
                and event.get("provider") == "google_drive"
                and event.get("verification_method") == "full_download_content_digest"
                and event.get("verification_status") == "pass"
            ):
                proofs[artifact_id] = {
                    "provider": "google_drive",
                    "destination": event.get("remote_url"),
                    "event_id": event.get("event_id"),
                    "verified_at": event.get("verified_at"),
                }
            elif schema == "wong-choi-artifact-mirror/v1":
                proofs.setdefault(
                    artifact_id,
                    {
                        "provider": "filesystem",
                        "destination": event.get("destination"),
                        "event_id": event.get("event_id"),
                        "verified_at": event.get("mirrored_at"),
                    },
                )

    artifacts: list[dict[str, Any]] = []
    domains: dict[str, dict[str, int]] = {}
    providers: set[str] = set()
    for artifact_id, record in sorted(records.items()):
        domain = str(record.get("domain") or "unknown")
        proof = proofs.get(artifact_id)
        summary = domains.setdefault(domain, {"known": 0, "verified": 0})
        summary["known"] += 1
        if proof:
            summary["verified"] += 1
            providers.add(str(proof["provider"]))
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "domain": domain,
                "artifact_class": record.get("artifact_class"),
                "cold_verified": bool(proof),
                **(proof or {}),
            }
        )
    known = len(artifacts)
    verified = sum(1 for artifact in artifacts if artifact["cold_verified"])
    missing = known - verified
    status = "invalid" if invalid_records else "ok" if known and not missing else "attention" if known else "no_data"
    return {
        "status": status,
        "known_artifacts": known,
        "verified_artifacts": verified,
        "unverified_artifacts": missing,
        "providers": sorted(providers),
        "domains": domains,
        "artifacts": artifacts,
        "invalid_records": invalid_records,
    }


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
    d1_backup = collect_d1_backup_status(state_root)
    catalog_cold = _catalog_cold_coverage(state_root)
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
    attention.extend(d1_backup.get("attention") or [])
    if cold["configured"] and not d1_backup.get("cold_verified"):
        attention.append("dashboard_d1_backup_cold_pending")
    if catalog_cold["status"] in {"attention", "invalid"}:
        attention.append("artifact_cold_backlog")
    return {
        "schema_version": "wong-choi-storage-status/v1",
        "status": "attention" if attention else "ok",
        "attention": attention,
        "tiers": {"hot": hot, "warm": warm, "cold": cold},
        "backups": {
            "dashboard_d1": d1_backup,
            "catalog_artifacts": catalog_cold,
        },
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
    d1 = ((payload.get("backups") or {}).get("dashboard_d1") or {})
    catalog_cold = ((payload.get("backups") or {}).get("catalog_artifacts") or {})
    hot_disk = hot.get("disk") or {}
    lines = [
        f"💾 Wong Choi Storage：{payload.get('status')}",
        f"HOT SSD：{hot.get('pressure')} · free {hot_disk.get('free_gib', 'N/A')} GiB",
        f"WARM 外置碟：{warm.get('status')} · {warm.get('path', '未設定')}",
        f"COLD Drive：{cold.get('status')} · {cold.get('path', '未設定')}",
        f"D1 backup：{d1.get('status')} · age {d1.get('age_hours', 'N/A')}h · "
        f"WARM {'係' if d1.get('warm_verified') else '否'} · COLD {'係' if d1.get('cold_verified') else '否'}",
        f"Artifact COLD：{catalog_cold.get('verified_artifacts', 0)}/"
        f"{catalog_cold.get('known_artifacts', 0)} · "
        f"{','.join(catalog_cold.get('providers') or []) or '未有provider proof'}",
    ]
    if payload.get("attention"):
        lines.append("留意：" + "、".join(payload["attention"]))
    lines.append("搬檔閘：copy → hash → restore → second copy → 批准後才刪本機")
    return "\n".join(lines)
