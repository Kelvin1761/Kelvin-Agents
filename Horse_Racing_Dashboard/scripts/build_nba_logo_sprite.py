"""Build the NBA club-crest sprite the dashboard jerseys reference with <use>.

The crests are downloaded once from the NBA's logo CDN and kept in the repo so
the dashboard never fetches them at view time (and still shows them offline).
Illustrator exports share class names (.st0, .st1 …) with different fills per
file, so inlining them as-is would recolour every crest with the last file's
rules: each class is folded into inline attributes and every id is prefixed
with the team code before the files become <symbol>s.

    python3 scripts/build_nba_logo_sprite.py            # download + rebuild
    python3 scripts/build_nba_logo_sprite.py --from DIR # rebuild from local SVGs
"""
import argparse
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

TEAM_IDS = {
    "ATL": 1610612737, "BOS": 1610612738, "CLE": 1610612739, "NOP": 1610612740,
    "CHI": 1610612741, "DAL": 1610612742, "DEN": 1610612743, "GSW": 1610612744,
    "HOU": 1610612745, "LAC": 1610612746, "LAL": 1610612747, "MIA": 1610612748,
    "MIL": 1610612749, "MIN": 1610612750, "BKN": 1610612751, "NYK": 1610612752,
    "ORL": 1610612753, "IND": 1610612754, "PHI": 1610612755, "PHX": 1610612756,
    "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759, "OKC": 1610612760,
    "TOR": 1610612761, "UTA": 1610612762, "MEM": 1610612763, "WAS": 1610612764,
    "DET": 1610612765, "CHA": 1610612766,
}
URL = "https://cdn.nba.com/logos/nba/{id}/primary/L/logo.svg"
OUT = Path(__file__).resolve().parents[1] / "assets" / "nba_team_logos.svg"


def _declarations(text):
    return {k.strip(): v.strip() for k, v in (d.split(":", 1) for d in text.split(";") if ":" in d)}


def symbol(team, svg):
    """One crest file as a self-contained <symbol id="nba-logo-TEAM">."""
    if re.search(r"<script|<foreignObject|\bon\w+\s*=|(?:xlink:)?href\s*=\s*[\"'](?!#)", svg, re.I):
        raise ValueError(f"{team}: unexpected active content in crest SVG")
    rules = {}
    for block in re.findall(r"<style[^>]*>(.*?)</style>", svg, re.S):
        for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", block):
            for selector in selectors.split(","):
                name = selector.strip()
                if name.startswith("."):
                    rules.setdefault(name[1:], {}).update(_declarations(body))
    svg = re.sub(r"<style[^>]*>.*?</style>", "", svg, flags=re.S)
    svg = re.sub(r"<\?xml.*?\?>|<!--.*?-->", "", svg, flags=re.S)

    def fold(match):
        attrs = {}
        for cls in match.group(1).split():
            attrs.update(rules.get(cls, {}))
        return " ".join(f'{k}="{v}"' for k, v in attrs.items())

    svg = re.sub(r'class="([^"]*)"', fold, svg)
    svg = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{team}-{m.group(1)}"', svg)
    svg = re.sub(r'(url\(#|href="#)([^)"]+)', lambda m: f"{m.group(1)}{team}-{m.group(2)}", svg)
    head = re.search(r"<svg\b[^>]*>", svg)
    view_box = re.search(r'viewBox="([^"]+)"', head.group(0)).group(1)
    body = svg[head.end():svg.rindex("</svg>")]
    body = re.sub(r"\s+", " ", body).replace("> <", "><").strip()
    return f'<symbol id="nba-logo-{team}" viewBox="{view_box}">{body}</symbol>'


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="source", help="Directory of <TEAM>.svg files instead of downloading.")
    args = parser.parse_args()
    source = Path(args.source) if args.source else Path(tempfile.mkdtemp(prefix="nba-logos-"))
    if not args.source:
        for team, team_id in TEAM_IDS.items():
            with urllib.request.urlopen(URL.format(id=team_id), timeout=30) as response:
                (source / f"{team}.svg").write_bytes(response.read())
    symbols = [symbol(team, (source / f"{team}.svg").read_text(encoding="utf-8")) for team in TEAM_IDS]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        "<!-- NBA club crests (trademarks of the NBA and its teams), from cdn.nba.com/logos; "
        "built by scripts/build_nba_logo_sprite.py -->\n"
        '<svg xmlns="http://www.w3.org/2000/svg" style="position:absolute;width:0;height:0;overflow:hidden" '
        'aria-hidden="true" focusable="false">' + "".join(symbols) + "</svg>\n",
        encoding="utf-8")
    print(f"{OUT}: {len(symbols)} crests, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    sys.exit(main())
