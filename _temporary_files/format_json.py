import json

data = {
  "source": "Bet365_Manual",
  "extraction_time": "2026-04-07",
  "game": {
    "matchup": "MIN Timberwolves @ IND Pacers"
  },
  "game_lines": {},
  "player_props": {
    "points": {
      "Julius Randle": {
        "jersey": "30",
        "last5": [],
        "lines": {"10": "1.02", "15": "1.066", "20": "1.29", "25": "1.89", "30": "3.30"}
      },
      "Ayo Dosunmu": {
        "jersey": "11",
        "last5": [],
        "lines": {"10": "1.033", "15": "1.38", "20": "2.35", "25": "5.25"}
      },
      "Naz Reid": {
        "jersey": "11",
        "last5": [],
        "lines": {"10": "1.025", "15": "1.86", "20": "3.75"}
      },
      "Jarace Walker": {
        "jersey": "5",
        "last5": [],
        "lines": {"10": "1.045", "15": "1.95", "20": "3.90"}
      },
      "Nah'Shon Hyland": {
        "jersey": "8",
        "last5": [],
        "lines": {"10": "1.055", "15": "2.00", "20": "4.00"}
      },
      "Donte DiVincenzo": {
        "jersey": "0",
        "last5": [],
        "lines": {"10": "1.033", "15": "2.35"}
      },
      "Rudy Gobert": {
        "jersey": "27",
        "last5": [],
        "lines": {"10": "1.05", "15": "2.82"}
      },
      "Kobe Brown": {
        "jersey": "24",
        "last5": [],
        "lines": {"10": "1.10"}
      },
      "Ethan Thompson": {
        "jersey": "55",
        "last5": [],
        "lines": {"10": "1.20"}
      },
      "Jalen Slawson": {
        "jersey": "18",
        "last5": [],
        "lines": {"10": "1.28"}
      },
      "Mike Conley": {
        "jersey": "10",
        "last5": [],
        "lines": {"10": "1.60"}
      }
    },
    "threes_made": {},
    "rebounds": {},
    "assists": {}
  }
}

with open("2026-04-08 NBA Analysis/Bet365_Odds_MIN_IND.json", "w") as f:
    json.dump(data, f, indent=4)
