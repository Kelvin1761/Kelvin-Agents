#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


RUN_LINE_RE = re.compile(
    r"^[A-Z][A-Za-z .'&()/-]+(?: \*\*\(TRIAL\)\*\*)? R\d+ \d{4}-\d{2}-\d{2} \d+m cond:",
    re.MULTILINE,
)
FACT_ROW_RE = re.compile(r"^\|\s*\d+\s*\|.*$", re.MULTILINE)


def audit(base_dir: Path) -> dict:
    formguide_files = [p for p in base_dir.glob("**/*Formguide.md") if p.is_file()]
    facts_files = [p for p in base_dir.glob("**/*Facts.md") if p.is_file()]

    run_lines = 0
    margin_lines = 0
    hc_lines = 0
    pf_lines = 0
    pf_l600_lines = 0
    pf_rt_lines = 0
    prize_lines = 0

    for path in formguide_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in RUN_LINE_RE.finditer(text):
            line = text[match.start(): text.find("\n", match.start())]
            run_lines += 1
            if "$" in line:
                prize_lines += 1
            if "margin:" in line:
                margin_lines += 1
            if "HC:" in line:
                hc_lines += 1
            if "PF[" in line:
                pf_lines += 1
            if re.search(r"PF\[.*Last600:", line):
                pf_l600_lines += 1
            if re.search(r"PF\[.*RT Rating:", line):
                pf_rt_lines += 1

    fact_rows = 0
    fact_official_rows = 0
    fact_trial_rows = 0
    fact_l600_rt_rows = 0

    for path in facts_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in FACT_ROW_RE.findall(text):
            cols = [col.strip() for col in line.strip().strip("|").split("|")]
            if len(cols) < 18:
                continue
            kind = cols[1]
            if kind not in {"Maiden/SW", "試閘"} and not re.match(r"BM\d+", kind):
                continue
            fact_rows += 1
            is_trial = "試閘" in kind
            if is_trial:
                fact_trial_rows += 1
            else:
                fact_official_rows += 1
            if cols[13] and cols[13] != "-":
                fact_l600_rt_rows += 1

    return {
        "base_dir": str(base_dir),
        "formguide_files": len(formguide_files),
        "facts_files": len(facts_files),
        "formguide_run_lines": run_lines,
        "formguide_prize_lines": prize_lines,
        "formguide_margin_token_lines": margin_lines,
        "formguide_hc_token_lines": hc_lines,
        "formguide_pf_token_lines": pf_lines,
        "formguide_pf_l600_lines": pf_l600_lines,
        "formguide_pf_rt_lines": pf_rt_lines,
        "facts_record_rows": fact_rows,
        "facts_official_rows": fact_official_rows,
        "facts_trial_rows": fact_trial_rows,
        "facts_l600_rt_rows": fact_l600_rt_rows,
        "coverage": {
            "formguide_prize": ratio(prize_lines, run_lines),
            "formguide_margin_token": ratio(margin_lines, run_lines),
            "formguide_hc_token": ratio(hc_lines, run_lines),
            "formguide_pf_token": ratio(pf_lines, run_lines),
            "formguide_pf_l600": ratio(pf_l600_lines, run_lines),
            "formguide_pf_rt": ratio(pf_rt_lines, run_lines),
            "facts_l600_rt": ratio(fact_l600_rt_rows, fact_rows),
        },
    }


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def main() -> None:
    from pathlib import Path as _Path
    _PROJECT_ROOT = _Path(__file__).resolve().parents[5]
    import sys as _sys; _sys.path.insert(0, str(_PROJECT_ROOT))
    from wongchoi_paths import AU_RACING as _AU_RACING
    parser = argparse.ArgumentParser(description="Audit AU extractor/Facts feature coverage.")
    parser.add_argument("--base-dir", default=str(_AU_RACING))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = audit(Path(args.base_dir))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"AU extraction feature audit: {result['base_dir']}")
    print(f"Formguide files: {result['formguide_files']} | Facts files: {result['facts_files']}")
    print(f"Formguide run lines: {result['formguide_run_lines']}")
    for key, value in result["coverage"].items():
        print(f"- {key}: {value:.1%}")
    print(f"Facts rows: {result['facts_record_rows']} | official: {result['facts_official_rows']} | trials: {result['facts_trial_rows']}")


if __name__ == "__main__":
    main()
