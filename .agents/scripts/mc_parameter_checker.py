#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
mc_parameter_checker.py — Monte Carlo Parameter Consistency Check

Scans a SIP changelog (JSON) for keywords that indicate the SIP touches
parameters also hardcoded in monte_carlo_core.py. Flags any that need
manual synchronization.

Usage:
  python mc_parameter_checker.py --sip-changelog "SIP_proposals.json" [--domain hkjc|au]

Output: JSON report of MC parameters that may need updating.

Version: 1.0.0
"""
import json, sys, argparse, re

# MC hardcoded parameters and their trigger keywords
MC_PARAMETER_MAP = {
    "compute_weight_adj": {
        "keywords": ["weight", "負磅", "頂磅", "top weight", "負重", "斤量"],
        "current_values": {
            "hkjc": {"heavy_threshold": 133, "light_threshold": 115, "unit": "lbs"},
            "au":   {"heavy_threshold": 62,  "light_threshold": 54,  "unit": "kg"},
        },
        "file": "monte_carlo_core.py",
        "line_ref": "compute_weight_adj() L91-L112",
    },
    "compute_freshness_factor": {
        "keywords": ["freshness", "久休", "復出", "layoff", "spell", "turnaround",
                     "休息", "days since", "放草"],
        "current_values": {
            "sweet_spot": "14-21 days → 1.01-1.02x",
            "concern": ">70 days → 0.97x",
            "severe": ">90 days → 0.92x",
        },
        "file": "monte_carlo_core.py",
        "line_ref": "compute_freshness_factor() L68-L88",
    },
    "stability_index": {
        "keywords": ["stability", "穩定性", "一致性", "consistency", "variance"],
        "current_values": {
            "high_threshold": 0.7,
            "mid_threshold": 0.5,
            "high_bonus": "1.03x",
            "mid_bonus": "1.01x",
        },
        "file": "monte_carlo_core.py",
        "line_ref": "monte_carlo_race() L204-L209",
    },
    "forgiveness_bonus": {
        "keywords": ["forgiveness", "寬恕", "pardoned", "excuse", "受困",
                     "流鼻血", "慢閘", "受阻"],
        "current_values": {
            "bonus": 0.03,
        },
        "file": "monte_carlo_core.py",
        "line_ref": "monte_carlo_race() L247",
    },
    "trainer_jockey_baseline": {
        "keywords": ["trainer", "練馬師", "jockey", "騎師", "win rate",
                     "勝率", "trainer signal"],
        "current_values": {
            "trainer_baseline": 0.15,
            "trainer_sensitivity": 0.5,
            "jockey_baseline": 0.10,
            "jockey_sensitivity": 0.3,
        },
        "file": "monte_carlo_core.py",
        "line_ref": "monte_carlo_race() L212-L215",
    },
    "barrier_adjustment": {
        "keywords": ["barrier", "檔位", "draw", "閘位", "gate"],
        "current_values": {
            "extreme_outside": ">= 85% → -0.03",
            "wide": ">= 75% → -0.02",
            "inside_rail": "<= 15% → +0.01",
        },
        "file": "monte_carlo_core.py",
        "line_ref": "compute_barrier_adj() L115-L134",
    },
    "risk_penalty": {
        "keywords": ["risk", "風險", "override", "penalty", "懲罰",
                     "red flag", "降級"],
        "current_values": {
            "4_markers": -0.15,
            "3_markers": -0.10,
            "2_markers": -0.05,
        },
        "file": "monte_carlo_core.py",
        "line_ref": "compute_risk_penalty() L137-L148",
    },
    "speed_energy_weights": {
        "keywords": ["speed weight", "energy weight", "權重", "composite",
                     "speed_weight", "energy_weight"],
        "current_values": {
            "speed_weight": 0.35,
            "energy_weight": 0.25,
        },
        "file": "monte_carlo_core.py",
        "line_ref": "monte_carlo_race() L151",
    },
}


def scan_sip_changelog(sip_data, domain="hkjc"):
    """Scan SIP proposals for MC parameter conflicts."""
    alerts = []

    # Flatten all SIP text content for keyword matching
    sip_text = json.dumps(sip_data, ensure_ascii=False).lower()

    for param_name, config in MC_PARAMETER_MAP.items():
        matched_keywords = []
        for kw in config["keywords"]:
            if kw.lower() in sip_text:
                matched_keywords.append(kw)

        if matched_keywords:
            alert = {
                "parameter": param_name,
                "matched_keywords": matched_keywords,
                "current_values": config["current_values"],
                "file": config["file"],
                "line_ref": config["line_ref"],
                "action": "⚠️ REVIEW NEEDED — SIP may require MC parameter sync",
            }
            # Add domain-specific values if available
            if isinstance(config["current_values"], dict) and domain in config["current_values"]:
                alert["domain_values"] = config["current_values"][domain]
            alerts.append(alert)

    return alerts


def main():
    parser = argparse.ArgumentParser(description="MC Parameter Consistency Checker")
    parser.add_argument("--sip-changelog", required=True, help="Path to SIP proposals JSON")
    parser.add_argument("--domain", choices=["hkjc", "au"], default="hkjc",
                        help="Racing domain (hkjc or au)")
    parser.add_argument("--output", help="Output JSON path (default: stdout)")
    args = parser.parse_args()

    # Load SIP changelog
    try:
        with open(args.sip_changelog, 'r', encoding='utf-8') as f:
            sip_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ SIP changelog not found: {args.sip_changelog}")
        sys.exit(1)
    except json.JSONDecodeError:
        # Try reading as text (markdown SIP proposals)
        with open(args.sip_changelog, 'r', encoding='utf-8') as f:
            sip_data = {"content": f.read()}

    # Scan
    alerts = scan_sip_changelog(sip_data, domain=args.domain)

    # Report
    report = {
        "domain": args.domain,
        "sip_file": args.sip_changelog,
        "total_parameters_checked": len(MC_PARAMETER_MAP),
        "alerts_count": len(alerts),
        "alerts": alerts,
        "status": "✅ No MC sync needed" if not alerts else "⚠️ MC parameter review required",
    }

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"✅ Report saved to {args.output}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    # Summary
    if alerts:
        print(f"\n⚠️ {len(alerts)} MC parameter(s) may need synchronization:")
        for a in alerts:
            print(f"  - {a['parameter']}: matched [{', '.join(a['matched_keywords'])}]")
            print(f"    → Check {a['file']} @ {a['line_ref']}")
    else:
        print("\n✅ No MC parameters affected by this SIP batch.")


if __name__ == "__main__":
    main()
