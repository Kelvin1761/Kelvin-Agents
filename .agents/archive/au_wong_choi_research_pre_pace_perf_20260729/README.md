# Archived AU research scripts

Archived on 2026-07-29 during the AU Wong Choi schema and simplification audit.

These scripts are historical experiments, not supported tuning entry points. They
either reference removed modules (`rank_adjustments`, `hidden_signal_rescue`),
removed scoring APIs (`PLACE_TIGHTENING_*`,
`soft_race_shape_modifier`, engine-level `get_dynamic_matrix_weights`) or use the
pre-merge matrix schema (`sectional` / `mx_sectional`) that was replaced by
`pace_perf` / `mx_pace_perf`. The archived `test_count.py`,
`test_mismatch.py`, and `test_regex.py` are import-unsafe one-off diagnostics;
`update_scripts.py` is an obsolete self-modifying migration utility.

Do not use their output to change live weights. The supported evidence path is:

1. `au_cached_walkforward_ml.py` for the versioned, canonical matrix dataset.
2. `au_clean_7d_weight_search.py` for expanding-window candidate selection plus
   an untouched terminal date holdout.
3. The live `racing_engine/matrix_mapper.py` schema as the single source of
   matrix keys and compatibility aliases.

Files are retained only for historical comparison.
