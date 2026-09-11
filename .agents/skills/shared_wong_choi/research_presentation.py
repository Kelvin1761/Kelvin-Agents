"""Read-only Stage 5 presentation, derived from a replay-verified review receipt.

This is a local projection/Telegram *preview*, not a sender or Dashboard deploy.
Hashes prove content consistency, not source truth, delivery or model approval.
Consumers must render registry/report strings as text, never trusted HTML.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from .research_index import _Reader, _safe, load_review_receipt


SCHEMA = "wong-choi-research-presentation/v1"
_DOMAINS = {"au": "AU", "hkjc": "HKJC", "tennis": "Tennis", "nba": "NBA"}


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _evidence_from_review_summary(summary_path, receipt_path, receipt):
    """Verify an optional historical review proof and return bounded evidence."""
    path = _safe(Path(summary_path))
    attempt = path.parent.parent
    if (path.name != "review-summary.json" or path.parent.name != "work"
            or not attempt.name.startswith("review-")
            or attempt.parent.name != receipt["domain"]):
        raise ValueError("review summary is outside its owned attempt")
    reader = _Reader(lambda: None, max_record_bytes=65536, max_total_bytes=262144)
    request, _ = reader.read(attempt / "request.json")
    completed, _ = reader.read(attempt / "completed.json")
    summary, _ = reader.read(path)
    from .research_review_runtime import verify_review_summary
    from .research_runner import ResearchRuntime
    runtime = ResearchRuntime(
        state_root=Path(request["state_root"]),
        warm_root=Path(request["warm_root"]),
        production_lock_paths=tuple(
            Path(item) for item in request["production_locks"]
        ),
        reserve_bytes=request["reserve_bytes"],
    )
    expected_attempt = _safe(
        runtime.warm_root / "research-phases" / receipt["domain"] / attempt.name
    )
    verify_review_summary(
        request=request, runtime=runtime, report_path=path, receipt=completed,
    )
    selected = [
        item for item in summary["processed"]
        if item["request_id"] == receipt["request_id"]
    ]
    if (attempt != expected_attempt or request["payload"]["domain"] != receipt["domain"]
            or len(selected) != 1
            or selected[0]["receipt_id"] != receipt["content_hash"]
            or _safe(Path(selected[0]["path"])) != _safe(Path(receipt_path))):
        raise ValueError("review summary does not own selected receipt")
    reader.recheck()
    reference = summary.get("storage_evidence")
    storage = None
    if reference is not None:
        if (summary.get("storage_evidence_status")
                != "verified_" + reference["storage_health"]):
            raise ValueError("review storage status mismatch")
        storage = {
            "health": reference["storage_health"],
            "observed_at": reference["observed_at"],
            "content_hash": reference["content_hash"],
        }
    reference = summary.get("process_liveness")
    liveness = None
    if reference is not None:
        expected_status = (
            "verified_complete"
            if reference["all_claimed_processes_verified"]
            else "verified_incomplete"
        )
        if (summary.get("process_liveness_evidence_status") != expected_status
                or summary.get("process_liveness_verified") is not True
                or reference["queue_index_hash"] != summary["index_hash"]):
            raise ValueError("review liveness status mismatch")
        liveness = {
            "content_hash": reference["content_hash"],
            "observed_at": reference["observed_at"],
            "queue_index_hash": reference["queue_index_hash"],
            "all_claimed_processes_verified": reference[
                "all_claimed_processes_verified"
            ],
            "counts": reference["counts"],
        }
    reference = summary.get("production_day_evidence")
    production_day = None
    if reference is not None:
        expected_status = (
            "verified_closed"
            if reference["production_day_closed"]
            else "verified_incomplete"
        )
        if summary.get("production_day_evidence_status") != expected_status:
            raise ValueError("review production-day status mismatch")
        production_day = {
            "content_hash": reference["content_hash"],
            "observed_at": reference["observed_at"],
            "production_day": reference["production_day"],
            "production_day_closed": reference["production_day_closed"],
            "operational_health": reference["operational_health"],
            "counts": reference["counts"],
            "closure_blockers": reference["closure_blockers"],
        }
    reference = summary.get("live_drift")
    drift = None
    if reference is not None:
        expected_status = (
            "verified_descriptive"
            if reference["status"] == "verified_descriptive"
            else "verified_" + reference["status"]
        )
        if (summary.get("live_drift_evidence_status") != expected_status
                or summary.get("live_drift_verified")
                is not reference["live_drift_verified"]
                or reference["metric_drift_verified"] is not False
                or reference["market_drift_verified"] is not False):
            raise ValueError("review live drift status mismatch")
        drift = {
            key: value for key, value in reference.items() if key != "path"
        }
    return {
        "storage": storage,
        "liveness": liveness,
        "production_day": production_day,
        "drift": drift,
    }


def prepare_review_presentation(receipt_path, *, review_summary_path=None):
    """Verify first, then project one domain from bounded receipt/proof reads.

    A future authorized sender must persist delivery evidence separately. Its
    dedup identity is registry/domain/request/version; a different payload under
    the same identity is a conflict, not a reason to silently send again. Merely
    computing this key does not acknowledge, suppress or deliver a notification.
    """
    receipt = load_review_receipt(receipt_path)
    evidence = (
        _evidence_from_review_summary(
            review_summary_path, receipt_path, receipt,
        )
        if review_summary_path is not None else {
            "storage": None, "liveness": None, "production_day": None,
            "drift": None,
        }
    )
    storage = evidence["storage"]
    liveness = evidence["liveness"]
    production_day = evidence["production_day"]
    drift = evidence["drift"]
    index, plan, domain = receipt["index"], receipt["plan"], receipt["domain"]
    experiments = [item for item in index["experiments"] if item["domain"] == domain]
    runs = [run for item in experiments for run in item["runs"]]
    choices = [choice for run in runs for choice in run["registered_decisions"]]
    queue = [{"job_id": item["job_id"], "status": item["status"], "process_alive": None}
             for item in index["queue"] if item["job"]["domain"] == domain]
    counts = {
        "experiments": len(experiments), "runs": len(runs),
        "run_states": dict(sorted(Counter(run["execution_state"] for run in runs).items())),
        "decisions": dict(sorted(Counter(choice["state"] for choice in choices).items())),
        "reports_not_supplied": sum(choice["report_verification"] == "not_supplied" for choice in choices),
        "reports_hash_linked": sum(choice["report_verification"] == "hash_and_lineage_verified_not_recomputed"
                                   for choice in choices),
    }
    ruler_mismatches = [item["spec_id"] for item in experiments if item["ruler_digest"] != plan["ruler_digest"]]
    projection = {
        "schema_version": SCHEMA, "domain": domain, "as_of": receipt["recorded_at"],
        "request_id": receipt["request_id"], "receipt_hash": receipt["content_hash"],
        "index_hash": index["content_hash"], "review_ruler_digest": plan["ruler_digest"],
        "request": next(item for item in plan["requests"] if item["request_id"] == receipt["request_id"]),
        "experiments": experiments, "queue": queue, "counts": counts,
        "other_ruler_experiment_ids": ruler_mismatches,
        "freeze_reasons": plan["freeze_reasons"], "findings": plan["findings"],
        "freeze_research_required": plan["freeze_research_required"],
        "human_review_required": plan["human_review_required"], "progress_only": plan["progress_only"],
        "verified_monitoring_samples": None,
        "production_day_evidence_status": (
            "verified_closed" if production_day and production_day["production_day_closed"]
            else "verified_incomplete" if production_day
            else "not_integrated"
        ),
        "storage_health": storage["health"] if storage else None,
        "live_drift_evidence_status": (
            "verified_descriptive"
            if drift and drift["status"] == "verified_descriptive"
            else "verified_" + drift["status"] if drift
            else "not_integrated"
        ),
        "live_drift": drift,
        "queue_completeness_verified": liveness is not None,
        "process_liveness_verified": liveness is not None,
        "evidence_scope": "receipt_snapshot_hash_and_lineage_not_source_reaudit",
        "safety_recomputed": False, "model_promotion_allowed": False,
        "rerun_scoring_allowed": False, "reevaluate_promotion_allowed": False,
    }
    if storage is not None:
        # Pin observation identity, not merely its health label. Existing
        # receipt-only payload hashes remain unchanged.
        projection["storage_evidence"] = storage
    if liveness is not None:
        projection["process_liveness"] = liveness
    if production_day is not None:
        projection["production_day_evidence"] = production_day
    projection["content_hash"] = _hash(projection)
    states = counts["decisions"]
    next_action = ("凍結研究／需要人手覆核" if plan["freeze_research_required"] else
                   "核對證據後再做 shadow review" if states.get("shadow_review_proposal") else
                   "檢視紀錄及補齊證據")
    # Fixed labels and bounded counts only: do not echo hypotheses, raw errors,
    # local paths, URLs or arbitrary report text into an eventual external chat.
    lines = [
        f"中央旺財 Stage 5｜{_DOMAINS[domain]} 研究摘要（本機預覽）",
        f"截至：{receipt['recorded_at']}",
        "本次只報進度，唔重判 promotion" if plan["progress_only"] else "只展示 review 紀錄，唔重判 promotion",
        f"已登記：實驗 {counts['experiments']}／執行紀錄 {counts['runs']}",
        f"判決紀錄：拒絕 {states.get('reject', 0)}／未有定論 {states.get('inconclusive', 0)}／"
        f"受阻 {states.get('blocked', 0)}／shadow review 提案 {states.get('shadow_review_proposal', 0)}",
        f"報告：hash／關聯已核對 {counts['reports_hash_linked']}／未附報告 {counts['reports_not_supplied']}",
        "合格監測樣本：未核實（manifest 行數唔等於 PIT／forward 樣本）",
        (
            "生產日：已完整核實"
            + (
                "（運行需留意）"
                if production_day["operational_health"] == "attention" else ""
            )
            if production_day and production_day["production_day_closed"]
            else (
                "生產日：證據未完整"
                f"（缺口 {len(production_day['closure_blockers'])}）"
                if production_day else "生產日：未接入"
            )
        ),
        (
            (
                "運行存活：來源已核實（運行 "
                f"{liveness['counts']['running_verified']}／未核實 "
                f"{liveness['counts']['claimed_liveness_unverified']}／非存活 "
                f"{liveness['counts']['claimed_not_alive']}）"
                if liveness else "運行存活：未核實"
            )
            + ("；儲存健康："
               + ("需留意" if storage["health"] == "attention" else "正常")
               + "（已核實時間點快照）"
               if storage else "；儲存健康：未接入")
        ),
        (
            (
                "特徵 drift：已核實（"
                + {"improved": "改善", "degraded": "轉差",
                   "unchanged": "持平"}[drift["direction"]]
                + f"；基準 {drift['baseline_records']}／當期 {drift['current_records']}）"
                if drift["status"] == "verified_descriptive"
                else (
                    "特徵 drift：證據不足"
                    if drift["status"] == "insufficient_data"
                    else "特徵 drift：來源未完整"
                )
                + f"（基準 {drift['baseline_records']}／當期 {drift['current_records']}）"
            )
            + "；模型指標／市場 drift：未核實"
            if drift else "特徵／模型指標／市場 drift：未接入"
        ),
        f"其他 ruler 嘅歷史實驗：{len(ruler_mismatches)}（唔當現行 ruler 評估）",
        f"下一步：{next_action}",
        "證據只屬截至當時嘅快照；未重算安全檢查，唔代表模型改善。",
        f"Review：{receipt['request_id']}",
        f"證據 hash：{receipt['content_hash']}",
        "未發送 Telegram，亦未批准部署、下注或模型升級。",
    ]
    telegram = {
        "status": "prepared_only", "text": "\n".join(lines), "parse_mode": None,
        "dedup_key": _hash({"schema": SCHEMA, "registry": index["registry_root"],
                           "domain": domain, "request_id": receipt["request_id"]}),
        "projection_hash": projection["content_hash"],
        "audience_requirement": "authorized_primary_only",
        "send_authorized": False, "delivery_confirmed": False,
    }
    telegram["content_hash"] = _hash(telegram)
    return {"projection": projection, "telegram": telegram}
