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
        return []

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

