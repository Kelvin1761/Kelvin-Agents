"""Strict historical singles point state machine; offline source qualification."""
from __future__ import annotations

import json
from pathlib import Path
import re

RULE_PATH = Path(__file__).with_name('slam_rules.json')
RULES = json.loads(RULE_PATH.read_text())


def set_rule(event, year, best_of, set_number):
    if best_of not in (3, 5) or not 1 <= set_number <= best_of:
        raise ValueError('unknown format/set number')
    law = next((r for r in RULES['deciding_set'].get(event, []) if r['first_year'] <= year <= r['last_year']), None)
    if law is None:
        raise ValueError('UNKNOWN historical rules')
    return law if set_number == best_of else RULES['nondeciding_set']


def uint(text):
    if not isinstance(text, str) or not re.fullmatch(r'0|[1-9]\d*', text):
        raise ValueError('invalid unsigned count')
    return int(text)


def display_score(points):
    a, b = points
    if min(a, b) >= 3:
        return ['40', '40'] if a == b else (['AD', '40'] if a > b else ['40', 'AD'])
    return [str((0, 15, 30, 40)[min(a, 3)]), str((0, 15, 30, 40)[min(b, 3)])]


class PointReplay:
    def __init__(self, event, year, best_of):
        set_rule(event, year, best_of, 1)
        self.event, self.year, self.best_of = event, year, best_of
        self.games, self.points, self.sets, self.total = [0, 0], [0, 0], [0, 0], [0, 0]
        self.set_scores = []
        self.next_server = None
        self.numeric_points = 0
        self.service_points, self.service_won = [0, 0], [0, 0]
        self.tb_count = 0
        self.last_terminal_score = None

    @property
    def winner(self):
        need = self.best_of // 2 + 1
        return 1 if self.sets[0] == need else (2 if self.sets[1] == need else 0)

    def step(self, server, winner):
        if self.winner:
            raise ValueError('point_after_terminal_match')
        if server not in (1, 2) or winner not in (1, 2):
            raise ValueError('invalid_server_or_point_winner')
        if self.next_server is None:
            self.next_server = server
        set_no, game_no = len(self.set_scores) + 1, sum(self.games) + 1
        law = set_rule(self.event, self.year, self.best_of, set_no)
        trigger = law['tiebreak_games']
        tb = trigger is not None and self.games == [trigger, trigger]
        index = sum(self.points)
        expected = self.next_server if not tb or index % 4 in (0, 3) else 3 - self.next_server
        if server != expected:
            raise ValueError('service_order_conflict')
        self.total[winner - 1] += 1
        self.service_points[server - 1] += 1
        self.service_won[server - 1] += server == winner
        self.numeric_points += 1
        self.points[winner - 1] += 1
        target = law['tiebreak_points'] if tb else 4
        won_game = max(self.points) >= target and abs(self.points[0] - self.points[1]) >= 2
        terminal_score = [str(p) for p in self.points] if tb else display_score(self.points)
        if won_game and not tb:
            terminal_score[winner - 1] = 'GAME'
        self.last_terminal_score = terminal_score
        game_winner = set_winner = 0
        if won_game:
            game_winner = winner
            self.games[winner - 1] += 1
            self.next_server = 3 - self.next_server
            self.points = [0, 0]
            if tb or (max(self.games) >= 6 and abs(self.games[0] - self.games[1]) >= 2):
                set_winner = winner
                self.sets[winner - 1] += 1
                self.set_scores.append(self.games.copy())
                self.tb_count += tb
        post_games = self.games.copy()
        score = ['0', '0'] if won_game else ([str(p) for p in self.points] if tb else display_score(self.points))
        if set_winner:
            self.games = [0, 0]
        return {'SetNo': str(set_no), 'GameNo': str(game_no), 'GameWinner': str(game_winner),
                'SetWinner': str(set_winner), 'P1GamesWon': str(post_games[0]), 'P2GamesWon': str(post_games[1]),
                'P1Score': score[0], 'P2Score': score[1],
                'P1PointsWon': str(self.total[0]), 'P2PointsWon': str(self.total[1])}


def elapsed_seconds(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+:\d{2}:\d{2}', value):
        return None
    h, m, s = map(int, value.split(':'))
    return h * 3600 + m * 60 + s if m < 60 and s < 60 else None


def replay(rows, event, year, best_of):
    state = PointReplay(event, year, best_of)
    errors, details, markers, seen, missing_scoreboard = {}, [], [], set(), {}
    maximum_elapsed, last_elapsed, missing_elapsed = 0, None, 0
    stopped = False
    # Explicit source-schema variants, established from raw columns/rows before
    # any source-augmentation fit. Never select a schema by candidate performance.
    cumulative_games = event in ('ausopen', 'frenchopen') and 2018 <= year <= 2021
    game_token = (event == 'frenchopen' and 2020 <= year <= 2021) or (event == 'ausopen' and year == 2021)
    def error(reason, number):
        errors[reason] = errors.get(reason, 0) + 1
        if len(details) < 20:
            details.append({'point': number, 'reason': reason})
    for row in rows:
        number = row.get('PointNumber')
        if number in seen:
            error('duplicate_point_key', number)
        seen.add(number)
        if number in ('0', '0X', '0Y'):
            markers.append(number)
            if (state.numeric_points or row.get('PointServer') != '0' or row.get('PointWinner') != '0'
                    or any(row.get(k) != '0' for k in ('P1Score', 'P2Score', 'P1GamesWon', 'P2GamesWon'))):
                error('invalid_nonplay_marker', number)
            continue
        seconds = elapsed_seconds(row.get('ElapsedTime'))
        if seconds is None:
            missing_elapsed += 1
        else:
            if last_elapsed is not None and seconds < last_elapsed:
                error('elapsed_clock_regression', number)
            last_elapsed = seconds
            maximum_elapsed = max(maximum_elapsed, seconds)
        if stopped:
            continue
        try:
            if uint(number) != state.numeric_points + 1:
                raise ValueError('nonconsecutive_point_number')
            previous_set_games = sum(sum(s) for s in state.set_scores)
            expected = state.step(uint(row.get('PointServer')), uint(row.get('PointWinner')))
            if cumulative_games:
                expected['GameNo'] = str(previous_set_games + int(expected['GameNo']))
            if game_token and expected['GameWinner'] != '0':
                expected['P1Score'], expected['P2Score'] = state.last_terminal_score
        except ValueError as e:
            error(str(e), number)
            stopped = True
            continue
        for k, value in expected.items():
            if row.get(k) in ('', None):
                missing_scoreboard[k] = missing_scoreboard.get(k, 0) + 1
            elif row[k] != value:
                error(k + '_postpoint_conflict', number)
    if not state.winner:
        error('no_terminal_match', None)
    return {'point_rows': len(rows), 'numeric_points_replayed': state.numeric_points,
            'nonplay_markers': markers, 'errors': errors, 'first_errors': details,
            'missing_scoreboard_counts': missing_scoreboard,
            'source_schema': {'game_number': 'cumulative_match' if cumulative_games else 'within_set',
                              'terminal_point_score': 'GAME_or_numeric_TB' if game_token else 'reset_zero'},
            'terminal_winner': state.winner, 'sets': state.set_scores, 'set_wins': state.sets,
            'total_points': state.total, 'service_points': state.service_points, 'service_won': state.service_won,
            'tiebreak_sets': state.tb_count, 'maximum_elapsed_seconds': maximum_elapsed,
            'elapsed_missing_rows': missing_elapsed, 'wall_clock_end_available': False,
            'state_machine_pass': not errors, 'full_scoreboard_verified': not errors and not missing_scoreboard,
            'format_is_supplied_not_inferred_from_terminal_score': True}
