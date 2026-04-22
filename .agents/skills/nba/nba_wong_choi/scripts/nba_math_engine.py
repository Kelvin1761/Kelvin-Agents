import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
nba_math_engine.py — NBA 前置數學計算引擎

將所有確定性數學運算從 LLM offload 到 Python，確保 100% 準確。
LLM 只需負責判斷性分析（情境調整、核心邏輯、風險評估）。

計算項目：
1. L10 均值 (AVG) / 中位數 (MED) / 標準差 (SD) / 變異系數 (CoV)
2. CoV 分級 (🛡️ / ✅ / ➖ / 🎲)
3. 隱含勝率 (1/賠率 × 100)
4. Edge (預估勝率 - 隱含勝率)
5. 命中率計算 (L10/L5/L3 命中盤口線嘅百分比)
6. Weighted AVG (近期加權平均)
7. 趨勢判斷 (↑/↓/—)

Usage:
  python nba_math_engine.py --l10 "28,31,25,33,29,27,30,26,34,28" --line 27.5 --odds 1.85
  python nba_math_engine.py --json '{"l10": [28,31,25,33,29,27,30,26,34,28], "line": 27.5, "odds": 1.85}'
  python nba_math_engine.py --batch input.json
"""
import sys, io, json, math, argparse
from dataclasses import dataclass, asdict
from typing import List, Optional

# Fix encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


@dataclass
class MathResult:
    """Structured output for LLM consumption."""
    # Input echo
    player: str = ""
    market: str = ""
    line: float = 0.0
    odds: float = 0.0

    # L10 Statistics
    l10_array: List[float] = None
    avg: float = 0.0
    med: float = 0.0
    sd: float = 0.0
    cov: float = 0.0
    cov_grade: str = ""

    # Weighted AVG (recent games weighted higher)
    weighted_avg: float = 0.0
    trend: str = ""  # ↑ / ↓ / —

    # Hit Rates
    hit_l10: float = 0.0  # percentage
    hit_l5: float = 0.0
    hit_l3: float = 0.0
    hit_l10_count: str = ""  # "8/10"
    hit_l5_count: str = ""
    hit_l3_count: str = ""

    # Miss Analysis
    miss_games: List[dict] = None  # [{game: 3, value: 22, deficit: -5.5}]

    # Implied Probability & Edge
    implied_prob: float = 0.0
    edge: float = 0.0  # requires est_prob input
    est_prob: float = 0.0

    # Status
    status: str = "ok"
    errors: List[str] = None

    def __post_init__(self):
        if self.l10_array is None:
            self.l10_array = []
        if self.miss_games is None:
            self.miss_games = []
        if self.errors is None:
            self.errors = []


def compute_stats(data: List[float]) -> tuple:
    """Compute AVG, MED, SD, CoV for a list of numbers."""
    n = len(data)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0

    avg = sum(data) / n

    sorted_data = sorted(data)
    if n % 2 == 0:
        med = (sorted_data[n // 2 - 1] + sorted_data[n // 2]) / 2
    else:
        med = sorted_data[n // 2]

    variance = sum((x - avg) ** 2 for x in data) / n
    sd = math.sqrt(variance)

    cov = sd / avg if avg != 0 else 0.0

    return round(avg, 2), round(med, 1), round(sd, 2), round(cov, 3)


def grade_cov(cov: float) -> str:
    """Grade CoV into categories."""
    if cov <= 0.15:
        return "🛡️ 穩定機器"
    elif cov <= 0.25:
        return "✅ 正常波動"
    elif cov <= 0.35:
        return "➖ 中高波動"
    else:
        return "🎲 神經刀"


def compute_weighted_avg(data: List[float]) -> float:
    """Compute weighted average. L10 order is newest -> oldest."""
    n = len(data)
    if n == 0:
        return 0.0
    weights = []
    for i in range(n):
        if i < 3:
            weights.append(1.5)
        elif i < 7:
            weights.append(1.0)
        else:
            weights.append(0.7)
    weighted_sum = sum(d * w for d, w in zip(data, weights))
    weight_total = sum(weights)
    return round(weighted_sum / weight_total, 2)


def compute_trend(data: List[float]) -> str:
    """Determine trend direction from L10 data.
    Compare L3 avg vs L10 avg.
    """
    if len(data) < 5:
        return "—"
    l3_avg = sum(data[:3]) / 3
    l10_avg = sum(data) / len(data)
    diff_pct = (l3_avg - l10_avg) / l10_avg * 100 if l10_avg != 0 else 0

    if diff_pct > 5:
        return "📈 上升"
    elif diff_pct < -5:
        return "📉 下降"
    else:
        return "— 持平"


def compute_hit_rate(data: List[float], line: float, is_over: bool = True) -> tuple:
    """Compute hit rate for a given line.
    Sportsbet 10+ = 10 or more, so we use >= for over.
    Returns (percentage, count_str, miss_details).
    """
    if not data:
        return 0.0, "0/0", []

    if is_over:
        hits = [1 for x in data if x >= line]
    else:
        hits = [1 for x in data if x <= line]

    hit_count = sum(hits)
    total = len(data)
    pct = round(hit_count / total * 100, 1)
    count_str = f"{hit_count}/{total}"

    # Miss analysis
    misses = []
    for i, x in enumerate(data):
        missed = (x < line) if is_over else (x > line)
        if missed:
            deficit = round(x - line, 1)
            misses.append({
                "game": i + 1,
                "value": x,
                "deficit": deficit
            })

    return pct, count_str, misses


def compute_implied_prob(odds: float) -> float:
    """Compute implied probability from decimal odds."""
    if odds <= 0:
        return 0.0
    return round(100 / odds, 2)


def compute_edge(est_prob: float, implied_prob: float) -> float:
    """Compute edge = estimated probability - implied probability."""
    return round(est_prob - implied_prob, 2)


def process_player(config: dict) -> dict:
    """Process a single player's math calculations.

    Expected config keys:
    - player: str (player name)
    - market: str (e.g., "Points", "Rebounds")
    - l10: list[float] (L10 game-by-game data)
    - line: float (betting line)
    - odds: float (decimal odds)
    - est_prob: float (optional — estimated win probability from LLM)
    - is_over: bool (optional — default True)
    """
    result = MathResult()
    result.player = config.get("player", "Unknown")
    result.market = config.get("market", "")

    l10 = config.get("l10", [])
    line = config.get("line", 0.0)
    odds = config.get("odds", 0.0)
    est_prob = config.get("est_prob", 0.0)
    is_over = config.get("is_over", True)

    # Validate L10
    if len(l10) != 10:
        result.errors.append(f"L10 數組長度 = {len(l10)}，應為 10")
        result.status = "warning"

    result.l10_array = l10
    result.line = line
    result.odds = odds
    result.est_prob = est_prob

    # 1. Basic Stats
    result.avg, result.med, result.sd, result.cov = compute_stats(l10)
    result.cov_grade = grade_cov(result.cov)

    # 2. Weighted AVG & Trend
    result.weighted_avg = compute_weighted_avg(l10)
    result.trend = compute_trend(l10)

    # 3. Hit Rates
    if line > 0:
        result.hit_l10, result.hit_l10_count, result.miss_games = compute_hit_rate(l10, line, is_over)
        result.hit_l5, result.hit_l5_count, _ = compute_hit_rate(l10[:5], line, is_over)
        result.hit_l3, result.hit_l3_count, _ = compute_hit_rate(l10[:3], line, is_over)

    # 4. Implied Probability
    if odds > 0:
        result.implied_prob = compute_implied_prob(odds)

    # 5. Edge (only if est_prob provided)
    if est_prob > 0:
        result.edge = compute_edge(est_prob, result.implied_prob)

    return asdict(result)


def format_output(result: dict) -> str:
    """Format result as human-readable text for LLM consumption."""
    lines = []
    lines.append(f"## 🐍 Python 數學引擎結果 — {result['player']} ({result['market']})")
    lines.append(f"")
    lines.append(f"### 基本統計")
    lines.append(f"- L10 逐場: {result['l10_array']}")
    lines.append(f"- 均值: {result['avg']} | 中位數: {result['med']}")
    lines.append(f"- SD: {result['sd']} | CoV: {result['cov']} → {result['cov_grade']}")
    lines.append(f"- Weighted AVG: {result['weighted_avg']} | 趨勢: {result['trend']}")
    lines.append(f"")
    lines.append(f"### 命中率（盤口線: {result['line']}）")
    lines.append(f"- L10: {result['hit_l10']}% ({result['hit_l10_count']})")
    lines.append(f"- L5: {result['hit_l5']}% ({result['hit_l5_count']})")
    lines.append(f"- L3: {result['hit_l3']}% ({result['hit_l3_count']})")
    if result['miss_games']:
        lines.append(f"- 未達標場次:")
        for m in result['miss_games']:
            lines.append(f"  - Game {m['game']}: {m['value']} (差距: {m['deficit']})")
    lines.append(f"")
    lines.append(f"### +EV 計算")
    lines.append(f"- 賠率: {result['odds']} → 隱含勝率: {result['implied_prob']}%")
    if result['est_prob'] > 0:
        lines.append(f"- 預估勝率: {result['est_prob']}%")
        lines.append(f"- Edge: {result['edge']}%")
    lines.append(f"")

    if result['errors']:
        lines.append(f"### ⚠️ 警告")
        for e in result['errors']:
            lines.append(f"- {e}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="NBA Math Engine — 前置確定性計算")
    parser.add_argument("--l10", type=str, help="L10 逐場數據（逗號分隔）")
    parser.add_argument("--line", type=float, default=0.0, help="盤口線")
    parser.add_argument("--odds", type=float, default=0.0, help="十進制賠率")
    parser.add_argument("--est-prob", type=float, default=0.0, help="預估勝率 (%)")
    parser.add_argument("--player", type=str, default="Player", help="球員名")
    parser.add_argument("--market", type=str, default="Props", help="市場類型")
    parser.add_argument("--under", action="store_true", help="legacy diagnostic only; NBA recommendations remain Over-only")
    parser.add_argument("--json", type=str, help="JSON 格式輸入（單個球員）")
    parser.add_argument("--batch", type=str, help="批次 JSON 檔案路徑（多個球員）")
    parser.add_argument("--output", choices=["text", "json"], default="text", help="輸出格式")

    args = parser.parse_args()

    results = []

    if args.batch:
        # Batch mode — process multiple players from JSON file
        with open(args.batch, 'r', encoding='utf-8') as f:
            batch_data = json.load(f)
        for player_config in batch_data.get("players", []):
            results.append(process_player(player_config))

    elif args.json:
        # JSON single player mode
        config = json.loads(args.json)
        results.append(process_player(config))

    elif args.l10:
        # CLI single player mode
        l10 = [float(x.strip()) for x in args.l10.split(",")]
        config = {
            "player": args.player,
            "market": args.market,
            "l10": l10,
            "line": args.line,
            "odds": args.odds,
            "est_prob": args.est_prob,
            "is_over": not args.under
        }
        results.append(process_player(config))

    else:
        print("❌ 必須提供 --l10, --json, 或 --batch 參數")
        sys.exit(1)

    # Output
    if args.output == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(format_output(r))
            print("---")


if __name__ == "__main__":
    main()
