"""Keep disputed source winners and overlapping score facts out of evidence."""
from __future__ import annotations

# Missing facts are not disagreements. Compare only overlapping measurements;
# choosing the newest/richest provider must not silently choose a score winner.
_SCORE_PATHS=tuple(f'$.player_{side}_{field}' for side in ('a','b')
                   for field in ('games','sets','aces','double_faults'))+tuple(
    f'$.sets[{n}].player_{side}_games' for n in range(5) for side in ('a','b'))+(
    '$.retired','$.walkover','$.incomplete_scoreline')


def _dispute_having(result: str, match: str) -> str:
    score=f"CASE WHEN json_valid({result}.score_json) THEN {result}.score_json ELSE '{{}}' END"
    return (
        f'COUNT(DISTINCT {result}.winner_player_id)>1'
        f' OR SUM(CASE WHEN {result}.winner_player_id IS NULL OR {result}.winner_player_id'
        f' NOT IN ({match}.player_a_id,{match}.player_b_id) THEN 1 ELSE 0 END)>0'
        f' OR SUM(CASE WHEN {result}.score_json IS NOT NULL AND '
        f"(NOT json_valid({result}.score_json) OR json_type({score})!='object') THEN 1 ELSE 0 END)>0"
        +f" OR SUM(CASE WHEN COALESCE(json_extract({score},'$.retired'),0)=0 "
         f"AND COALESCE(json_extract({score},'$.incomplete_scoreline'),0)=0 "
         f"AND ((json_extract({score},'$.player_a_sets')>=2 AND "
         f"json_extract({score},'$.player_a_sets')>json_extract({score},'$.player_b_sets') AND {result}.winner_player_id!={match}.player_a_id) "
         f"OR (json_extract({score},'$.player_b_sets')>=2 AND "
         f"json_extract({score},'$.player_b_sets')>json_extract({score},'$.player_a_sets') AND {result}.winner_player_id!={match}.player_b_id)) THEN 1 ELSE 0 END)>0"
        +''.join(f" OR COUNT(DISTINCT json_extract({score},'{path}'))>1" for path in _SCORE_PATHS)
    )


def conflicting_result_matches(conn) -> set[int]:
    conflicts={int(row[0]) for row in conn.execute(
        f'''SELECT r.match_id FROM match_results r JOIN matches m ON m.id=r.match_id
        GROUP BY r.match_id HAVING {_dispute_having('r','m')}''')}
    columns={row['name'] for row in conn.execute('PRAGMA table_info(matches)')}
    if 'fixture_status' in columns:
        conflicts.update(int(r[0]) for r in conn.execute("SELECT id FROM matches WHERE fixture_status='DISPUTED'"))
    return conflicts


def result_agreement_clause(alias: str = 'p', column: str = 'match_id') -> str:
    """Internal SQL predicate; history-settled aces may have no result row."""
    return (f'NOT EXISTS (SELECT 1 FROM match_results rc JOIN matches cm ON cm.id=rc.match_id '
            f'WHERE rc.match_id={alias}.{column} GROUP BY rc.match_id '
            f"HAVING {_dispute_having('rc','cm')})")


def score_fact_values(score: dict) -> dict:
    values={f'$.{k}':v for k,v in score.items() if f'$.{k}' in _SCORE_PATHS and v is not None}
    sets=score.get('sets')
    if isinstance(sets,list):
        for n,item in enumerate(sets[:5]):
            if isinstance(item,dict):
                for side in ('a','b'):
                    key=f'player_{side}_games'
                    if item.get(key) is not None:
                        values[f'$.sets[{n}].{key}']=item[key]
    return values
