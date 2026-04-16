#!/usr/bin/env python3
"""
preflight_environment_check.py — Shared Pre-flight Environment Scanner

Scans the workspace for suspicious files that may have been created by
the LLM to bypass the orchestrator or game the system.

Usage:
  python3 .agents/scripts/preflight_environment_check.py <target_dir> [--domain hkjc|au|nba]
"""
import os
import sys
import json
import argparse
import time

# Files that are ALLOWED to exist in the target directory
ALLOWED_EXTENSIONS_IN_TARGET = {'.md', '.json', '.xlsx', '.csv', '.txt', '.numbers', '.DS_Store'}

# Known safe Python scripts in the .agents tree (basename only)
KNOWN_AGENT_SCRIPTS = {
    'fill_hkjc_verdicts.py', 'instinct_evaluator.py', 'generate_nba_reports.py', 'debug_racecard.py', 'monte_carlo_nba.py', 'test_live_sections.py', 'inject_sips.py', 'claw_racenet_scraper.py', 'test_fetch_racecard.py', 'seo_checker.py', 'test_bs4_sections_2.py', 'monte_carlo_core.py', 'verify_nba_math.py', 'fetch_nba_h2h.py', 'narrative_postmortem_extractor.py', 'nba_report_generator.py', 'reflector_verdict_validator.py', 'verify_math.py', 'validator_result_comparator.py', 'bet365_parser.py', 'fetch_nba_pbp.py', 'compile_analysis_template_hkjc.py', 'extract_starter_pdf.py', 'extractor.py', 'fetch_injury_domino.py', 'cron_morning_trigger.py', 'audit_all.py', 'validate_nba_output.py', 'inject_fact_anchors.py', 'preflight_environment_check.py', 'safe_file_writer.py', 'engine_health_scanner.py', 'reflector_report_skeleton.py', 'schema_validator.py', 'prizepicks_scanner.py', 'monte_carlo_hkjc.py', 'predict_speed_map.py', 'test_bs4_full.py', 'wong_choi_orchestrator.py', 'ecosystem_drift_detector.py', 'test_runner.py', 'compute_hkjc_matrix.py', 'fast_extract_results.py', 'inject_hkjc_batch.py', 'au_speed_map_generator.py', 'observation_log_manager.py', 'test_fetch_header.py', 'debug_html.py', 'grading_engine.py', 'compute_nba_props.py', 'track_bias_tuner.py', 'test_fetch.py', 'lighthouse_audit.py', 'compile_final_report.py', 'api_validator.py', 'inject_hkjc_fact_anchors.py', 'generate_skeleton.py', 'create_hkjc_logic_skeleton.py', 'generate_nba_sgm_reports.py', 'test_safe_file_writer.py', 'auto_preview.py', 'send_telegram_msg.py', 'compile_analysis_template.py', 'combine_data.py', 'lint_runner.py', 'type_coverage.py', 'convert_rules.py', 'scrape_hkjc_horse_profile.py', 'completion_gate_v2.py', 'nba_db_logger.py', 'claw_discover_v5.py', 'react_performance_checker.py', 'compile_nba_report.py', 'scratch_handler.py', 'reflector_auto_stats.py', 'extract_formguide.py', 'test_parse_racecard.py', 'generate_hkjc_reports.py', 'agent_health_scanner.py', 'send_telegram_doc.py', 'session_manager.py', 'compute_rating_matrix_au.py', 'validate_analysis.py', 'verify_all.py', 'compute_rating_matrix_hkjc.py', 'test_fetch_header2.py', 'ux_audit.py', 'test_python_template_flow.py', 'session_state_manager.py', 'hkjc_profile_scraper.py', 'antigravity_mapper.py', 'geo_checker.py', 'au_orchestrator.py', 'nba_math_engine.py', 'verify_form_accuracy.py', 'claw_bet365_receiver.py', 'test_bs4_sections.py', 'checklist.py', 'nba_backtester.py', 'mobile_audit.py', 'extract_racecard.py', 'mc_parameter_checker.py', 'engine_coverage_matrix.py', 'security_scan.py', 'extract_verdicts.py', 'rule_trigger_tracker.py', 'monte_carlo_au.py', 'verify_grading.py', 'nba_extractor.py', 'extract_race_result.py', 'batch_extract_results.py', 'claw_bet365_odds.py', 'track_predictor.py', 'agent_evaluator.py', 'test_bs4.py', 'extract_results.py', 'i18n_checker.py', 'prefill_horse_data.py', 'claw_profile_scraper.py', 'playwright_runner.py', 'crawl_hkjc_jockey_trainer.py', 'hkjc_orchestrator.py', 'verify_analysis_au.py', 'extract_formguide_playwright.py', 'nba_orchestrator.py', 'validator_scope_analyzer.py', 'accessibility_checker.py', 'verify_props_hits.py', 'fetch_nba_results.py', '_wong_choi_injector.py', 'setup_chromadb_rag.py', 'test_racenet.py', 'session_cost_tracker.py', 'extract_formguide_data.py', 'compute_rating_matrix.py', 'generate_reports.py', 'claw_sportsbet_odds.py', 'run_monte_carlo.py', 'create_au_logic_skeleton.py', 'batch_extract.py', 'sip_conflict_scanner.py', 'inject_mc_au.py', 'generate_meeting_intel.py', 'inspect_meeting_nuxt.py'
}


def scan_target_dir(target_dir):
    """Scan target analysis directory for suspicious .py files."""
    issues = []
    if not os.path.isdir(target_dir):
        return issues

    for f in os.listdir(target_dir):
        full_path = os.path.join(target_dir, f)
        if os.path.isfile(full_path):
            _, ext = os.path.splitext(f)
            if ext in ['.py', '.sh', '.bat', '.js']:
                issues.append({
                    'type': 'DUMMY_SCRIPT',
                    'severity': 'CRITICAL',
                    'file': full_path,
                    'message': f'可疑腳本 ({ext}) 喺分析目錄: {f}'
                })
    return issues


def scan_agents_tree(session_start_time=None):
    """Scan .agents directory for newly created/modified scripts."""
    issues = []
    agents_dir = ".agents"
    if not os.path.isdir(agents_dir):
        return issues

    for root, dirs, files in os.walk(agents_dir):
        # Skip __pycache__ and hidden dirs, and _archive
        dirs[:] = [d for d in dirs if not d.startswith('__') and not d.startswith('.') and d not in ('_archive', 'venv', 'node_modules', 'lib', 'bin', 'include')]
        for f in files:
            if f.endswith('.py'):
                if f not in KNOWN_AGENT_SCRIPTS:
                    full_path = os.path.join(root, f)
                    issues.append({
                        'type': 'UNKNOWN_SCRIPT',
                        'severity': 'CRITICAL',
                        'file': full_path,
                        'message': f'未知 Python 腳本 (唔喺白名單): {f}'
                    })
                elif session_start_time:
                    full_path = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(full_path)
                        if mtime > session_start_time:
                            issues.append({
                                'type': 'MODIFIED_SCRIPT',
                                'severity': 'WARNING',
                                'file': full_path,
                                'message': f'已知腳本被修改 (session 後): {f}'
                            })
                    except OSError:
                        pass
    return issues


def scan_runtime_dir(target_dir):
    """Scan .runtime directory for stale context files."""
    issues = []
    runtime_dir = os.path.join(target_dir, '.runtime')
    if os.path.isdir(runtime_dir):
        for f in os.listdir(runtime_dir):
            if f.endswith('.py'):
                issues.append({
                    'type': 'RUNTIME_SCRIPT',
                    'severity': 'CRITICAL',
                    'file': os.path.join(runtime_dir, f),
                    'message': f'Python 腳本喺 .runtime 目錄: {f}'
                })
    return issues


def main():
    parser = argparse.ArgumentParser(description='Preflight Environment Check')
    parser.add_argument('target_dir', help='Target analysis directory to scan')
    parser.add_argument('--domain', choices=['hkjc', 'au', 'nba'], default='hkjc')
    parser.add_argument('--session-start', type=float, help='Session start timestamp')
    args = parser.parse_args()

    print("=" * 60)
    print("🛡️ Preflight Environment Check")
    print("=" * 60)

    all_issues = []

    # 1. Scan target directory
    all_issues.extend(scan_target_dir(args.target_dir))

    # 2. Scan .agents tree
    all_issues.extend(scan_agents_tree(args.session_start))

    # 3. Scan .runtime directory
    all_issues.extend(scan_runtime_dir(args.target_dir))

    critical_count = sum(1 for i in all_issues if i['severity'] == 'CRITICAL')
    warning_count = sum(1 for i in all_issues if i['severity'] == 'WARNING')

    if not all_issues:
        print("✅ 環境檢查通過 — 未發現可疑檔案")
        sys.exit(0)

    # Report issues
    for issue in all_issues:
        icon = '🚨' if issue['severity'] == 'CRITICAL' else '⚠️'
        print(f"  {icon} [{issue['type']}] {issue['message']}")
        print(f"     → {issue['file']}")

    # Write to error log
    error_log_path = os.path.join(args.target_dir, '_preflight_issues.json')
    try:
        with open(error_log_path, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': time.time(),
                'domain': args.domain,
                'issues': all_issues
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    if critical_count > 0:
        print(f"\n🛑 [BLOCKED] 發現 {critical_count} 個嚴重問題！")
        print("請先清理可疑檔案後再重新執行 Orchestrator！")
        print("如果係你自己建立嘅合法檔案，請將佢加入白名單。")
        sys.exit(2)
    else:
        print(f"\n⚠️ 發現 {warning_count} 個警告，但唔影響執行。")
        sys.exit(0)


if __name__ == '__main__':
    main()
