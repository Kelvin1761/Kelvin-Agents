# Antigravity AST Codebase Map

## `agent_health_scanner.py`

* **Function `find_workspace_root()`** - Walk up from script location to find workspace root.
* **Function `parse_frontmatter(text)`** - Extract YAML-like frontmatter from markdown.
* **Function `scan_agent(skill_path, tier, fix_suggestions)`** - Scan a single agent SKILL.md and return findings.
* **Function `calculate_score(findings)`** - Calculate health score from findings.
* **Function `discover_agents(root, tier1_dir, tier2_dir, target, tier_filter)`** - Discover all agent directories.
* **Function `list_all_agents(agents)`** - List all agents with name/description for Mode A Phase 3 matching.
* **Function `main()`**

## `antigravity_mapper.py`

* **Function `get_docstring(node)`**
* **Function `format_args(args_node)`**
* **Function `extract_ast_info(filepath)`**
* **Function `should_ignore(path_obj)`**
* **Function `build_repomap(target_dir, output_file)`**

## `au_speed_map_generator.py`

* **Class `HorseProfile`**
* **Function `parse_racecard(filepath: str)`** - Parse a Racecard.md file and extract horse profiles.
* **Function `classify_run_style(horse: HorseProfile)`** - Classify a horse's run style based on Last 10 string.
* **Function `suggest_pace_type(horses, distance: int)`** - Suggest overall pace type based on leader count and distance.
* **Function `format_speed_map(horses, pace_type: str, leader_count: int, rationale: str)`** - Generate formatted Speed Map draft.
* **Function `main()`**

## `compile_final_report.py`

* **Function `compile_reports(target_dir)`**

## `completion_gate_v2.py`

* **Function `check_au_hkjc_format(text: str, domain: str)`**
* **Function `check_au_hkjc_words(text: str, domain: str)`**
* **Function `check_nba_format(text: str)`** - Strengthened NBA format check — aligned with HKJC/AU rigor.
* **Function `check_nba_words(text: str)`** - NBA overall word count check — minimum 1500 for a complete game analysis.
* **Function `main()`**

## `compute_hkjc_matrix.py`

* **Function `parse_md(filepath)`**
* **Function `build_tables(ranked, race_id)`**
* **Function `main()`**

## `compute_rating_matrix.py`

* **Function `count_dimensions(dims: dict)`** - Count ✅, ➖, ❌ by dimension type.
* **Function `lookup_base_grade(counts: dict)`** - Look up the base grade from the synthesis table. Returns (grade, rule_description).
* **Function `apply_core_constraint(base_grade: str, counts: dict, dims: dict)`** - Apply core constraint: core ❌ → cap at B+, with exception.
* **Function `apply_micro_adjustments(grade: str, micro_up: list, micro_down: list)`** - Apply micro-adjustments (±1 grade max).
* **Function `compute_grade(horse: dict)`** - Compute the full rating for a horse.
* **Function `format_matrix_block(result: dict)`** - Format the complete 📊 評級矩陣 block.
* **Function `rank_horses(results)`** - Rank horses by grade (primary), ✅ count (secondary), ❌ count (tertiary).
* **Function `generate_verdict(ranked)`** - Generate the Top 4 verdict scaffold with pre-filled rankings.
* **Function `generate_csv(ranked, race_id: str)`** - Generate the Part 5 CSV block.
* **Function `main()`**

## `ecosystem_drift_detector.py`

* **Function `find_workspace_root()`** - Walk up from script location to find workspace root.
* **Function `parse_tree_structure(reference_text)`** - Extract directory names from markdown tree structure in ecosystem_reference.md.
* **Function `scan_actual_dirs(scan_dir, depth)`** - Scan actual filesystem directories up to given depth.
* **Function `scan_agent_table(reference_text)`** - Extract agent names from the markdown table in ecosystem_reference.md.
* **Function `main()`**

## `engine_coverage_matrix.py`

* **Function `extract_engine_rules(resources_dir)`** - Extract all rules/steps/overrides from resource files.
* **Function `check_coverage(rules, analysis_dirs)`** - Check which rules are covered by actual analysis output.
* **Function `main()`**

## `engine_health_scanner.py`

* **Function `scan_stale_logic(resources_dir, domain)`** - 4d-1: Check for references to retired/transferred jockeys/trainers.
* **Function `scan_disconnected_logic(resources_dir)`** - 4d-2: Check for SIP cross-references pointing to non-existent steps/rules.
* **Function `scan_data_freshness(resources_dir)`** - 4d-4: Check file modification dates, flag stale files.
* **Function `main()`**

## `extract_formguide_data.py`

* **Function `parse_formguide(filepath: str)`** - Parse Formguide.md and extract structured data per horse.
* **Function `extract_race_entries(block: str)`** - Extract individual race entries from a horse block, skipping trials.
* **Function `extract_all_dates(block: str)`** - Extract ALL dates from a horse block, including trials.
* **Function `compute_fitness_arc(entries: list, all_dates)`** - Compute fitness arc from race entries.
* **Function `compute_l600_trend(entries)`** - Compute L600 trend from race entries.
* **Function `compute_condition_profile(stats: dict)`** - Compute condition suitability profile.
* **Function `compute_flucs_direction(flucs)`** - Determine market movement direction from fluctuations.
* **Function `parse_racecard_weights(filepath: str)`** - Parse Racecard.md to extract current race weights per horse number.
* **Function `compute_weight_differentials(horses: list, racecard_weights: dict)`** - Compute weight differential data for all horses.
* **Function `format_markdown(horses)`** - Format extracted data as compact Markdown for LLM consumption.
* **Function `format_json(horses)`** - Format extracted data as JSON.
* **Function `main()`**

## `extract_verdicts.py`

* **Function `extract_csv(filepath)`**

## `generate_skeleton.py`

* **Function `detect_mode(text: str)`** - Auto-detect whether this is AU or HKJC format.
* **Function `parse_facts_md_au(text: str)`** - Parse AU-format Facts.md and extract per-horse blocks.
* **Function `parse_facts_md_hkjc(text: str)`** - Parse HKJC-format Facts.md and extract per-horse blocks.
* **Function `_extract_between(block: str, start_marker: str, end_marker: str)`** - Extract text from line containing start_marker to line before end_marker.
* **Function `_extract_from(block: str, start_marker: str)`** - Extract text from line containing start_marker to end of block.
* **Function `generate_horse_skeleton_hkjc(horse: dict)`** - Generate a HKJC analysis skeleton for one horse.
* **Function `generate_horse_skeleton_au(horse: dict)`** - Generate an AU analysis skeleton for one horse (original logic).
* **Function `generate_final_verdict(horses)`** - Generate a pre-formatted Final Verdict section.
* **Function `main()`**

## `hkjc_profile_scraper.py`

* **Function `parse_margin_cn(margin_str: str)`** - Parse Chinese race result margin to numeric lengths.
* **Function `scrape_race_result(result_url: str, timeout: int)`** - Scrape a HKJC race results page (SSR HTML).
* **Function `compute_form_lines(entries, max_races: int, rate_limit: float)`** - Compute form lines (賽績線) for a horse.
* **Function `format_form_lines_report(horse_name: str, form_lines: dict)`** - Format form lines result as markdown.
* **Function `main()`**

## `inject_fact_anchors.py`
* [SyntaxError] Could not parse AST: EOL while scanning string literal (<unknown>, line 1413)


## `inject_hkjc_fact_anchors.py`
* [SyntaxError] Could not parse AST: EOL while scanning string literal (<unknown>, line 752)


## `inject_sips.py`

* (No classes or functions found)

## `instinct_evaluator.py`

* **Function `parse_instincts_from_registry(registry_path: str)`** - Parse instinct entries from the registry markdown file.
* **Function `extract_hit_rate_from_reflector(report_path: str)`** - Extract hit rate data from a Reflector report.
* **Function `extract_results_from_backtest(report_path: str)`** - Extract results from NBA backtester output.
* **Function `evaluate_instincts(instincts, domain: str, reflector_data: dict, backtest_data: dict)`** - Evaluate instincts and compute updated confidence scores.
* **Function `format_evolution_report(results, domain: str)`** - Format the instinct evolution report.
* **Function `main()`**

## `narrative_postmortem_extractor.py`

* **Function `classify_incident_keywords(text)`** - Classify stewards/incident report text into categories.
* **Function `parse_running_positions(text)`** - Extract running position data from results text.
* **Function `parse_sectional_times(text)`** - Extract sectional times from results text.
* **Function `compute_deterioration(times)`** - Compute deterioration rate from sectional times.
* **Function `parse_picks(text)`**
* **Function `parse_results(text)`**
* **Function `extract_postmortem(results_text, analysis_text, race_num, domain)`** - Extract postmortem data for failed picks in a single race.
* **Function `print_postmortem(pm_data)`** - Print formatted postmortem report.
* **Function `main()`**

## `nba/compile_nba_report.py`

* **Function `compile_reports(target_dir)`**

## `nba/cron_morning_trigger.py`

* **Function `send_telegram_message(message)`**
* **Function `trigger_hermes_pipeline(date_str)`**

## `nba/fetch_injury_domino.py`

* **Function `analyze_domino_effect(team, players_out)`**

## `nba/fetch_nba_h2h.py`

* **Function `fetch_h2h_historic_data(team_a, team_b, stat_type)`**
* **Function `calculate_h2h_probability_injection(team_a, team_b, current_line)`** - Compares the historical average to the current bookmaker line.

## `nba/nba_orchestrator.py`

* **Function `setup_directory(target_date)`**
* **Function `collect_hardcore_math(team_a, team_b, line, target_dir, game_idx)`**
* **Function `trigger_nba_analyst(context_file, game_idx, target_dir)`**
* **Function `run_compilation(target_dir)`**
* **Function `main()`**

## `observation_log_manager.py`

* **Function `parse_log(path)`** - Parse observation_log.md into structured data.
* **Function `write_log(path, data)`** - Write structured data back to observation_log.md.
* **Function `check_dedup(existing_obs, new_pattern)`** - Check if new pattern overlaps with existing observations.
* **Function `main()`**

## `reflector_report_skeleton.py`

* **Function `parse_picks(text)`**
* **Function `parse_grades(text)`**
* **Function `parse_results(text)`**
* **Function `find_analysis_files(d)`**
* **Function `extract_race_num(fn)`**
* **Function `split_results_by_race(text)`**
* **Function `compute_hits(picks, results)`**
* **Function `generate_skeleton(analysis_dir, results_file, domain, venue, date_str)`**
* **Function `main()`**

## `reflector_verdict_validator.py`

* **Function `check_section_completeness(text, domain)`** - Check if all required sections are present.
* **Function `check_verdict_evidence(text)`** - Check that each verdict has ≥2 evidence points.
* **Function `check_sip_references(text, resources_dir)`** - Check that SIP references point to real resource files.
* **Function `check_unfilled_placeholders(text)`** - Count remaining {{LLM_FILL}} placeholders.
* **Function `check_hit_rate_tables(text)`** - Verify hit rate tables have actual data, not placeholders.
* **Function `check_verdict_statistics(text)`** - Check that verdict statistics section is filled.
* **Function `main()`**

## `rule_trigger_tracker.py`

* **Function `extract_defined_rules(resources_dir)`** - Extract all rule/SIP definitions from resource files.
* **Function `scan_analysis_files(analysis_dirs, rules)`** - Scan analysis files for rule triggers.
* **Function `classify_rules(rules, total_races)`** - Classify rules by trigger health.
* **Function `main()`**

## `run_monte_carlo.py`

* **Function `parse_facts_md(filepath)`** - Parses a Facts.md file to extract horse data from the Markdown tables.
* **Function `parse_margin(margin_str)`**
* **Function `run_simulation(horses_data, iterations)`** - Runs Monte Carlo simulations.
* **Function `inject_markdown_table(analysis_path, simulation_results)`** - Finds the <!-- MONTE_CARLO_PYTHON_INJECT_HERE --> tag in the analysis markdown
* **Function `export_csv(csv_path, simulation_results)`**
* **Function `process_directory(target_dir)`**

## `safe_file_writer.py`

* **Function `make_result(success: bool, message: str, target: str, lines: int, bytes_written: int, method: str)`**
* **Class `TimeoutError(Exception)`** - Raised when a file operation times out.
* **Function `_timeout_handler(signum, frame)`**
* **Function `_compute_checksum(file_path: str)`** - Compute SHA256 checksum of a file.
* **Function `_write_via_wltm(decoded_text: str, target_path: Path, write_mode: str, encoding: str, timeout: int)`** - Write-Local-Then-Move strategy:
* **Function `_write_direct(decoded_text: str, target_path: Path, write_mode: str, encoding: str)`** - Legacy direct write (fallback when WLTM fails or is disabled).
* **Function `main()`**

## `scrape_hkjc_horse_profile.py`

* **Function `parse_margin(margin_str: str)`** - Convert HKJC margin string to numeric lengths.
* **Function `parse_running_positions(pos_str: str)`** - Parse running positions string into list of ints.
* **Function `parse_time_to_seconds(time_str: str)`** - Convert HKJC time format to seconds.
* **Function `scrape_horse_profile(horse_id: str, timeout: int)`** - Scrape HKJC horse profile page (SSR HTML).
* **Function `compute_weight_trend(entries, today_weight)`** - Compute weight trend from horse profile entries.
* **Function `detect_gear_changes(entries, today_gear)`** - Detect gear changes between today and last race.
* **Function `compute_margin_trend(entries)`** - Compute margin trend from numeric margins.
* **Function `compute_rating_trend(entries)`** - Compute rating movement trend.
* **Function `compute_running_pi(entries)`** - Compute Position Index from precise running positions.
* **Function `format_profile_report(profile: dict, today_weight: int, today_gear: str)`** - Format the scraped profile into a readable report.
* **Function `main()`**

## `session_cost_tracker.py`

* **Function `count_tokens_estimate(text: str)`** - Estimate token count from text content.
* **Function `scan_au_hkjc(target_dir: str, batch_size: int, domain: str)`** - Scan AU or HKJC analysis directory for cost metrics.
* **Function `scan_nba(target_dir: str)`** - Scan NBA analysis directory for cost metrics.
* **Function `format_report(data: dict)`** - Format the cost report for terminal output.
* **Function `save_csv(data: dict, target_dir: str)`** - Append cost report to CSV history file.
* **Function `main()`**

## `session_state_manager.py`

* **Function `get_state_path(target_dir)`**
* **Function `load_state(target_dir)`**
* **Function `save_state(target_dir, data)`**
* **Function `main()`**

## `setup_chromadb_rag.py`

* **Function `init_chroma()`**
* **Function `semantic_search(collection, query_text, n_results)`**

## `sip_conflict_scanner.py`

* **Function `classify_effect(text)`** - Classify whether a SIP rule has positive, negative, or mixed effect.
* **Function `classify_dimensions(text)`** - Identify which dimensions a SIP affects.
* **Function `extract_step(text)`** - Extract the Step reference from SIP description.
* **Function `extract_conditions(text)`** - Extract trigger conditions from SIP description.
* **Function `parse_sip_index(path)`** - Parse the SIP index file to extract all SIP definitions.
* **Function `parse_resource_files(resources_dir)`** - Parse all resource files to find inline SIP rules.
* **Function `detect_direction_conflicts(sips)`** - Detect SIPs that affect the same dimension in opposite directions.
* **Function `detect_duplicate_counting(sips)`** - Detect SIPs that may cause double-counting on the same factor.
* **Function `detect_cross_references(sips, contexts)`** - Detect SIPs that reference each other (potential deadlock).
* **Function `detect_deprecated_references(sips, contexts)`** - Detect references to deprecated SIPs in active resource files.
* **Function `main()`**

## `test_safe_file_writer.py`

* **Function `run_writer(target: str, content: str, mode: str, dry_run: bool, use_stdin: bool, no_wltm: bool, timeout: int)`** - Helper to invoke safe_file_writer.py and return parsed JSON result.
* **Class `TestSafeFileWriterWLTM`** - WLTM (Write-Local-Then-Move) mode tests.
  * `def setUp(self)`
  * `def tearDown(self)`
  * `def test_01_wltm_basic_write(self)` - WLTM mode writes and moves file correctly.
  * `def test_02_wltm_overwrite_existing(self)` - WLTM mode overwrites existing files.
  * `def test_03_wltm_append(self)` - WLTM mode appends content correctly.
  * `def test_04_wltm_creates_parent_dirs(self)` - WLTM mode creates parent directories.
  * `def test_05_staging_dir_cleanup(self)` - WLTM staging file is cleaned up after successful move.
  * `def test_06_no_wltm_flag(self)` - --no-wltm flag forces direct write.
  * `def test_07_method_field_present(self)` - Result always contains method field.
* **Class `TestSafeFileWriterCore`** - Core functionality tests (work in both WLTM and direct modes).
  * `def setUp(self)`
  * `def tearDown(self)`
  * `def test_01_basic_overwrite(self)` - Basic overwrite to a new file.
  * `def test_02_overwrite_existing(self)` - Overwrite replaces existing content.
  * `def test_03_create_new_file(self)` - Create mode succeeds for new files.
  * `def test_04_create_existing_fails(self)` - Create mode fails if file already exists.
  * `def test_05_append(self)` - Append mode adds to existing content.
  * `def test_06_chinese_and_emoji(self)` - Handles Chinese characters and emojis correctly.
  * `def test_07_backticks_and_brackets(self)` - Handles Markdown backticks, brackets, and special chars.
  * `def test_08_large_file_2000_lines(self)` - Stress test: 2000+ lines of realistic analysis content.
  * `def test_09_stdin_mode(self)` - Reading Base64 from stdin works correctly.
  * `def test_10_dry_run(self)` - Dry run validates without writing.
  * `def test_11_auto_create_parents(self)` - Automatically creates parent directories.
  * `def test_12_line_count(self)` - Line count in result matches actual content.
  * `def test_13_line_count_no_trailing_newline(self)` - Line count handles content without trailing newline.
* **Class `TestSafeFileWriterErrors`** - Error handling tests.
  * `def test_empty_content(self)` - Empty content returns error.
  * `def test_invalid_base64(self)` - Invalid Base64 returns decode error.
* **Class `TestSafeFileWriterPythonFile`** - Test writing .py files — the most common deadlock trigger.
  * `def setUp(self)`
  * `def tearDown(self)`
  * `def test_write_python_file(self)` - Writing a .py file via WLTM works correctly.
  * `def test_write_large_python_file(self)` - Writing a large .py file (extractor script) via WLTM.

## `validator_result_comparator.py`

* **Function `parse_picks(text)`**
* **Function `parse_results(text)`**
* **Function `split_results_by_race(text)`**
* **Function `compare_race(picks, results)`** - Compare blind test picks vs actual results. Returns structured verdict.
* **Function `print_race_verdict(race_num, result)`** - Print formatted verdict for one race.
* **Function `main()`**

## `validator_scope_analyzer.py`

* **Function `parse_sip_changelog(text)`** - Parse SIP changelog entries with scope tags.
* **Function `extract_race_conditions(analysis_dir)`** - Extract race conditions from analysis files.
* **Function `match_scope(sip_scope, race_conditions)`** - Check if a SIP scope matches race conditions.
* **Function `analyze_scope(sips, races)`** - Determine which races need full blind test.
* **Function `main()`**

## `verify_analysis_au.py`

* **Function `verify_file(filepath)`**

## `verify_form_accuracy.py`

* **Function `parse_last10(last10_str: str)`** - Decode AU Last 10 string. '0' = 10th, 'x' = skip.
* **Function `is_trial_venue(venue: str, distance_str: str)`** - Heuristic: detect if a venue/distance combo is likely a trial.
* **Function `parse_racecard_horses(text: str)`** - Parse Racecard to get {horse_num: {...}}.
* **Function `extract_settled_positions(fg_text: str, horse_num: int, horse_name: str)`** - Extract Settled positions from the most recent races for a specific horse.
* **Function `parse_analysis_horses(text: str)`** - Parse Analysis.md to get {horse_num: {form_sequence, last_finish_claim}}.
* **Function `verify(racecard_horses: dict, analysis_horses: dict, fg_text: str)`** - Cross-reference and return list of mismatches.
* **Function `main()`**

## `wong_choi_orchestrator.py`

* **Function `get_target_dir(date, venue)`**
* **Function `run_extraction(mode, url, target_dir)`**
* **Function `trigger_agent_analysis(mode, target_dir, race_number)`**
* **Function `compile_results(target_dir)`**
* **Function `main()`**
