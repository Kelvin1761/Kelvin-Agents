from __future__ import annotations
import logging
from datetime import date, timedelta
from tennis_wc.providers.http import get_json
from tennis_wc.providers.tennis_provider_base import TennisProvider

logger = logging.getLogger(__name__)

class EspnTennisProvider(TennisProvider):
    provider_name = 'espn'

    def healthcheck(self) -> bool:
        try:
            get_json('https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard')
            return True
        except Exception:
            return False

    def fetch_upcoming_matches(self, date_str: str) -> list[dict]:
        formatted_date = date_str.replace('-', '')
        results = []
        for tour in ['atp', 'wta']:
            url = f'https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard'
            params = {'dates': formatted_date}
            try:
                body = get_json(url, params=params)
            except Exception as e:
                logger.error(f'Failed to fetch ESPN {tour} scoreboard: {e}')
                continue
            events = body.get('events', [])
            for event in events:
                groupings = event.get('groupings', [])
                for grouping in groupings:
                    competitions = grouping.get('competitions', [])
                    for competition in competitions:
                        match_date = competition.get('date', '')[:10]
                        # Filter matches for the requested date specifically
                        if match_date != date_str:
                            continue
                        normalised = self._normalise_match(event, competition, tour.upper())
                        if normalised:
                            normalised['analysis_date'] = date_str
                            results.append(normalised)
        return results

    def fetch_historical_matches(self, start_date: str, end_date: str) -> list[dict]:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        current = start
        results = []
        while current <= end:
            date_str = current.isoformat()
            formatted_date = date_str.replace('-', '')
            for tour in ['atp', 'wta']:
                url = f'https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard'
                params = {'dates': formatted_date}
                try:
                    body = get_json(url, params=params)
                except Exception as e:
                    logger.error(f'Failed to fetch ESPN historical {tour} scoreboard: {e}')
                    continue
                for event in body.get('events', []):
                    for grouping in event.get('groupings', []):
                        for competition in grouping.get('competitions', []):
                            match_date = competition.get('date', event.get('date', ''))[:10]
                            if match_date != date_str or not _is_completed(competition):
                                continue
                            normalised = self._normalise_history_match(event, competition, tour.upper())
                            results.extend(normalised)
            current += timedelta(days=1)
        return results

    def fetch_match_stats(self, match_id: str) -> dict:
        return {}

    def fetch_player_profile(self, player_id: str) -> dict:
        return {}

    def fetch_player_stats(self, player_id: str) -> dict:
        return {}

    def fetch_rankings(self, tour: str, date: str | None = None) -> list[dict]:
        return []

    def fetch_tournaments(self, start_date: str, end_date: str) -> list[dict]:
        return []

    def _get_tournament_metadata(self, name: str, match_date: str) -> dict:
        from .metadata_utils import infer_tournament_metadata
        return infer_tournament_metadata(name, match_date)

    def _normalise_match(self, event: dict, competition: dict, tour: str) -> dict | None:
        competitors = competition.get('competitors', [])
        if len(competitors) < 2:
            return None
        
        p1_node = competitors[0]
        p2_node = competitors[1]
        
        p1_athlete = p1_node.get('athlete', {})
        p2_athlete = p2_node.get('athlete', {})
        
        match_date = competition.get('date', event.get('date', ''))[:10]
        round_info = competition.get('round', {})
        
        tournament_name = event.get('name', '')
        meta = self._get_tournament_metadata(tournament_name, match_date)
        
        return {
            'id': str(competition.get('id')),
            'tour': tour,
            'match_date': match_date,
            'player_a_id': str(p1_node.get('id')),
            'player_b_id': str(p2_node.get('id')),
            'player_a_name': p1_athlete.get('displayName'),
            'player_b_name': p2_athlete.get('displayName'),
            'player_a_current_rank': p1_node.get('curatedRank', {}).get('current'),
            'player_b_current_rank': p2_node.get('curatedRank', {}).get('current'),
            'tournament_id': str(event.get('id', 'unknown')),
            'tournament_name': tournament_name.split(' - ')[0],
            'tournament_level': meta["level"],
            'surface': meta["surface"],
            'round': round_info.get('displayName', 'UNKNOWN'),
            'market_event_id': str(competition.get('id')),
            'raw': competition
        }

    def _normalise_history_match(self, event: dict, competition: dict, tour: str) -> list[dict]:
        match = self._normalise_match(event, competition, tour)
        if not match:
            return []
        competitors = competition.get('competitors', [])
        rows = []
        for idx, competitor in enumerate(competitors[:2]):
            athlete = competitor.get('athlete', {})
            opponent = competitors[1 - idx]
            opponent_athlete = opponent.get('athlete', {})
            rows.append(
                {
                    'id': f"{competition.get('id')}-{idx + 1}",
                    'tour': tour,
                    'match_date': match['match_date'],
                    'player_id': str(competitor.get('id')),
                    'opponent_id': str(opponent.get('id')),
                    'player_name': athlete.get('displayName'),
                    'opponent_name': opponent_athlete.get('displayName'),
                    'won': _competitor_won(competitor, opponent),
                    'surface': match.get('surface'),
                    'tournament_id': match.get('tournament_id'),
                    'tournament_level': match.get('tournament_level'),
                    'round': match.get('round'),
                    'format': 'BO5' if 'men' in str(event.get('name', '')).lower() and 'french open' in str(event.get('name', '')).lower() else 'BO3',
                    'raw': competition,
                }
            )
        return rows


def _is_completed(competition: dict) -> bool:
    status_type = (competition.get('status') or {}).get('type') or {}
    name = str(status_type.get('name') or status_type.get('state') or '').lower()
    if name in {'status_final', 'final', 'post'}:
        return True
    return bool(status_type.get('completed'))


def _competitor_won(competitor: dict, opponent: dict) -> bool:
    if competitor.get('winner') is not None:
        return bool(competitor.get('winner'))
    try:
        own_score = float(competitor.get('score'))
        opp_score = float(opponent.get('score'))
    except (TypeError, ValueError):
        return False
    return own_score > opp_score
