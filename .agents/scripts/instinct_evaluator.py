#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
Instinct Evaluator for Wong Choi Analysis Pipeline
Inspired by ECC continuous-learning-v2 instinct model.

Evaluates historical SIP/improvement entries against actual results,
updates confidence scores, and suggests promotions/deprecations.

Usage:
    # AU/HKJC — after Reflector report
    python3 .agents/scripts/instinct_evaluator.py "{TARGET_DIR}" \
      --registry ".agents/skills/shared_instincts/instinct_registry.md" \
      --domain au \
      --reflector-report "{REFLECTOR_REPORT_PATH}"

    # NBA — after backtester
    python3 .agents/scripts/instinct_evaluator.py "{TARGET_DIR}" \
      --registry ".agents/skills/shared_instincts/instinct_registry.md" \
      --domain nba \
      --backtest-report "{BACKTEST_REPORT_PATH}"
"""

import argparse
import os
import re
import sys
from pathlib import Path
from datetime import datetime


def parse_instincts_from_registry(registry_path: str) -> list[dict]:
    """Parse instinct entries from the registry markdown file."""
    instincts = []
    
    try:
        text = Path(registry_path).read_text(encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Could not read registry: {e}")
        return instincts
    
    # Parse YAML-like blocks between --- markers
    blocks = re.findall(r'---\n(.*?)---', text, re.DOTALL)
    
    for block in blocks:
        instinct = {}
        for line in block.strip().split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # Try numeric conversion
                try:
                    if '.' in value:
                        value = float(value)
                    elif value.isdigit():
                        value = int(value)
                except (ValueError, AttributeError):
                    pass
                instinct[key] = value
        
        if instinct.get('id'):
            instincts.append(instinct)
    
    return instincts


def extract_hit_rate_from_reflector(report_path: str) -> dict:
    """Extract hit rate data from a Reflector report."""
    try:
        text = Path(report_path).read_text(encoding="utf-8")
    except Exception as e:
        return {"error": f"Could not read report: {e}"}
    
    data = {
        "golden_rate": None,
        "good_rate": None,
        "minimum_rate": None,
        "sip_mentions": [],
        "false_positives": [],
        "false_negatives": [],
    }
    
    # Extract rates
    rate_patterns = {
        "golden_rate": r'黃金標準[率率]?\s*[：:]\s*\d+/\d+\s*\((\d+(?:\.\d+)?)%\)',
        "good_rate": r'良好結果[率率]?\s*[：:]\s*\d+/\d+\s*\((\d+(?:\.\d+)?)%\)',
        "minimum_rate": r'最低門檻[率率]?\s*[：:]\s*\d+/\d+\s*\((\d+(?:\.\d+)?)%\)',
    }
    for key, pattern in rate_patterns.items():
        match = re.search(pattern, text)
        if match:
            data[key] = float(match.group(1))
    
    # Extract SIP mentions
    sip_mentions = re.findall(r'SIP-[\w\-]+', text)
    data["sip_mentions"] = list(set(sip_mentions))
    
    # Extract False Positives/Negatives sections
    fp_section = re.search(r'False Positives.*?\n(.*?)(?=\n##|\n---|\Z)', text, re.DOTALL)
    if fp_section:
        data["false_positives"] = re.findall(r'\|\s*R?\d+\s*\|', fp_section.group(1))
    
    fn_section = re.search(r'False Negatives.*?\n(.*?)(?=\n##|\n---|\Z)', text, re.DOTALL)
    if fn_section:
        data["false_negatives"] = re.findall(r'\|\s*R?\d+\s*\|', fn_section.group(1))
    
    return data


def extract_results_from_backtest(report_path: str) -> dict:
    """Extract results from NBA backtester output."""
    try:
        text = Path(report_path).read_text(encoding="utf-8")
    except Exception as e:
        return {"error": f"Could not read report: {e}"}
    
    data = {
        "total_predictions": 0,
        "hits": 0,
        "misses": 0,
        "hit_rate": 0.0,
    }
    
    # Parse hit/miss counts
    hit_match = re.search(r'命中\s*(\d+)\s*注', text)
    total_match = re.search(r'共\s*(\d+)\s*注', text)
    
    if hit_match:
        data["hits"] = int(hit_match.group(1))
    if total_match:
        data["total_predictions"] = int(total_match.group(1))
        data["misses"] = data["total_predictions"] - data["hits"]
        if data["total_predictions"] > 0:
            data["hit_rate"] = round(data["hits"] / data["total_predictions"] * 100, 1)
    
    return data


def evaluate_instincts(instincts: list[dict], domain: str, 
                       reflector_data: dict = None, 
                       backtest_data: dict = None) -> list[dict]:
    """Evaluate instincts and compute updated confidence scores."""
    results = []
    
    domain_map = {"au": "au-racing", "hkjc": "hkjc-racing", "nba": "nba"}
    target_domain = domain_map.get(domain, domain)
    
    for inst in instincts:
        if inst.get("domain") != target_domain:
            continue
        if inst.get("status") == "deprecated":
            continue
        
        result = {
            "id": inst["id"],
            "domain": inst["domain"],
            "category": inst.get("category", "unknown"),
            "old_confidence": inst.get("confidence", 0.5),
            "new_confidence": inst.get("confidence", 0.5),
            "hit_count": inst.get("hit_count", 0),
            "miss_count": inst.get("miss_count", 0),
            "action": "unchanged",
            "reason": "",
        }
        
        # For AU/HKJC: check if SIP was mentioned in reflector report
        if domain in ("au", "hkjc") and reflector_data:
            sip_id = inst.get("source_sip", inst["id"])
            mentioned = any(sip_id in m for m in reflector_data.get("sip_mentions", []))
            
            if mentioned:
                # SIP was relevant to today's analysis
                # Check overall hit rate to determine direction
                golden = reflector_data.get("golden_rate")
                minimum = reflector_data.get("minimum_rate")
                
                if golden is not None and golden >= 30:
                    result["new_confidence"] = min(0.95, result["old_confidence"] + 0.05)
                    result["hit_count"] += 1
                    result["action"] = "confidence_up"
                    result["reason"] = f"覆盤驗證正確 (黃金標準 {golden}%)"
                elif minimum is not None and minimum < 50:
                    result["new_confidence"] = max(0.20, result["old_confidence"] - 0.10)
                    result["miss_count"] += 1
                    result["action"] = "confidence_down"
                    result["reason"] = f"覆盤驗證表現差 (最低門檻 {minimum}%)"
                else:
                    result["action"] = "neutral"
                    result["reason"] = "覆盤提及但表現中性"
        
        # For NBA: evaluate based on overall hit rate
        elif domain == "nba" and backtest_data:
            hit_rate = backtest_data.get("hit_rate", 0)
            if hit_rate >= 60:
                result["new_confidence"] = min(0.95, result["old_confidence"] + 0.05)
                result["hit_count"] += 1
                result["action"] = "confidence_up"
                result["reason"] = f"回測命中率高 ({hit_rate}%)"
            elif hit_rate < 40:
                result["new_confidence"] = max(0.20, result["old_confidence"] - 0.10)
                result["miss_count"] += 1
                result["action"] = "confidence_down"
                result["reason"] = f"回測命中率低 ({hit_rate}%)"
        
        # Check for status changes
        if result["new_confidence"] < 0.30:
            result["action"] = "suggest_deprecate"
            result["reason"] += " → Confidence < 0.30，建議 deprecate"
        elif result["new_confidence"] > 0.85:
            result["action"] = "suggest_promote"
            result["reason"] += " → Confidence > 0.85，建議升級為 Core Rule"
        
        # Check for consecutive misses
        if result["miss_count"] >= 2 and result["action"] not in ("suggest_deprecate",):
            consecutive = result["miss_count"] - result["hit_count"]
            if consecutive >= 2:
                result["action"] = "needs_review"
                result["reason"] += " → 連續 2+ 次錯誤，需要 review"
        
        result["new_confidence"] = round(result["new_confidence"], 2)
        results.append(result)
    
    return results


def format_evolution_report(results: list[dict], domain: str) -> str:
    """Format the instinct evolution report."""
    if not results:
        return f"📊 INSTINCT EVOLUTION REPORT ({domain.upper()})\n{'=' * 50}\n⚠️ 未搵到任何 {domain.upper()} domain 嘅 instinct。請先完成一次覆盤以初始化 instinct registry。"
    
    lines = [
        f"",
        f"🧬 INSTINCT EVOLUTION REPORT ({domain.upper()})",
        f"{'=' * 50}",
        f"📅 Evaluation Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"📊 Instincts Evaluated: {len(results)}",
        f"",
    ]
    
    # Group by action
    up = [r for r in results if r["action"] == "confidence_up"]
    down = [r for r in results if r["action"] == "confidence_down"]
    promote = [r for r in results if r["action"] == "suggest_promote"]
    deprecate = [r for r in results if r["action"] == "suggest_deprecate"]
    review = [r for r in results if r["action"] == "needs_review"]
    neutral = [r for r in results if r["action"] in ("neutral", "unchanged")]
    
    if up:
        lines.append("### ✅ 上升中 (Confidence ↑)")
        for r in up:
            lines.append(f"  - {r['id']}: {r['old_confidence']:.2f} → {r['new_confidence']:.2f} | {r['reason']}")
        lines.append("")
    
    if down:
        lines.append("### ❌ 下跌中 (Confidence ↓)")
        for r in down:
            lines.append(f"  - {r['id']}: {r['old_confidence']:.2f} → {r['new_confidence']:.2f} | {r['reason']}")
        lines.append("")
    
    if promote:
        lines.append("### 🌟 建議升級為 Core Rule")
        for r in promote:
            lines.append(f"  - {r['id']}: confidence {r['new_confidence']:.2f} — 可嵌入引擎 resource 檔案")
        lines.append("")
    
    if deprecate:
        lines.append("### 🗑️ 建議 Deprecate")
        for r in deprecate:
            lines.append(f"  - {r['id']}: confidence {r['new_confidence']:.2f} — {r['reason']}")
        lines.append("")
    
    if review:
        lines.append("### ⚠️ 需要 Review")
        for r in review:
            lines.append(f"  - {r['id']}: {r['reason']}")
        lines.append("")
    
    if neutral:
        lines.append(f"### ➖ 中性/未變動: {len(neutral)} 個 instincts")
        lines.append("")
    
    lines.append(f"{'=' * 50}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Wong Choi Instinct Evaluator")
    parser.add_argument("target_dir", type=str, help="Path to analysis target directory")
    parser.add_argument("--registry", type=str, required=True,
                        help="Path to instinct_registry.md")
    parser.add_argument("--domain", type=str, choices=["au", "hkjc", "nba"], required=True,
                        help="Analysis domain")
    parser.add_argument("--reflector-report", type=str, default=None,
                        help="Path to Reflector report (AU/HKJC)")
    parser.add_argument("--backtest-report", type=str, default=None,
                        help="Path to NBA backtester report")
    args = parser.parse_args()
    
    # Parse registry
    instincts = parse_instincts_from_registry(args.registry)
    
    if not instincts:
        print(f"⚠️ Instinct registry 係空嘅或無法解析。")
        print(f"   首次覆盤後，instincts 會自動從 SIP index / improvement log 遷移。")
        print(f"   請先完成一次覆盤 / 回測。")
        sys.exit(0)
    
    # Load evaluation data
    reflector_data = None
    backtest_data = None
    
    if args.domain in ("au", "hkjc") and args.reflector_report:
        reflector_data = extract_hit_rate_from_reflector(args.reflector_report)
        if "error" in reflector_data:
            print(f"⚠️ {reflector_data['error']}")
    
    if args.domain == "nba" and args.backtest_report:
        backtest_data = extract_results_from_backtest(args.backtest_report)
        if "error" in backtest_data:
            print(f"⚠️ {backtest_data['error']}")
    
    # Evaluate
    results = evaluate_instincts(instincts, args.domain, reflector_data, backtest_data)
    
    # Output
    report = format_evolution_report(results, args.domain)
    print(report)


if __name__ == "__main__":
    main()
