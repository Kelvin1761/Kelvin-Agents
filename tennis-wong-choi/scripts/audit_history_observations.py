"""Read-only canonical-observation diagnostic; never rebuilds or promotes Elo."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from itertools import groupby
import json
from pathlib import Path
import sqlite3

from tennis_wc.features import canonical_history


def audit(groups):
    counts=Counter()
    examples=[]
    for rows in groups:
        result=canonical_history.select_canonical_history(rows)
        counts['raw_rows']+=len(rows)
        counts['selected_rows']+=len(result.rows)
        counts['held_rows']+=len(result.audit['held'])
        counts['collapsed_extra_rows']+=sum(len(g['member_ids'])-1 for g in result.audit['collapsed'])
        counts['candidate_groups']+=1
        for entry in result.audit['held']:
            counts['held_'+entry['reason']]+=1
        if (result.audit['held'] or result.audit['collapsed']) and len(examples)<50:
            examples.append(result.audit)
    assert counts['raw_rows']==counts['selected_rows']+counts['held_rows']+counts['collapsed_extra_rows']
    return {'policy':canonical_history.POLICY,'counts':dict(counts),'examples':examples,
            'limitations':['Diagnostic only; held rows are not declared false or deleted.',
                           'Different recorded dates and unmapped provider event namespaces remain unresolved.',
                           'This does not establish pricing-time availability or qualify a model promotion.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--db',type=Path)
    inputs.add_argument('--input-json',type=Path)
    parser.add_argument('--since')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    connection=None
    try:
        if args.input_json:
            source=json.loads(args.input_json.read_text())
            groups=(item['rows'] for item in source)
        else:
            connection=sqlite3.connect(f'{args.db.resolve().as_uri()}?mode=ro',uri=True)
            connection.row_factory=sqlite3.Row
            where='WHERE match_date>=?' if args.since else ''
            cursor=connection.execute(f'''SELECT * FROM player_match_history {where}
                ORDER BY player_id,opponent_id,match_date,id''',(args.since,) if args.since else ())
            groups=(list(rows) for _,rows in groupby(cursor,lambda r:(r['player_id'],r['opponent_id'],r['match_date'])))
        result=audit(groups)
    finally:
        if connection is not None:
            connection.close()
    source_path=args.input_json or args.db
    result['source']=str(source_path.resolve())
    result['source_bytes']=source_path.stat().st_size
    if args.input_json:
        result['source_sha256']=hashlib.sha256(source_path.read_bytes()).hexdigest()
    result['implementation_sha256']=hashlib.sha256(Path(canonical_history.__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['counts']))


if __name__=='__main__':
    main()
