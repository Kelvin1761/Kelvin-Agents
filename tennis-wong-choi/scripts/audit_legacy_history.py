"""Read-only legacy history source-context audit; optional backed-up, exact-plan quarantine."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3

from tennis_wc.database.history_audit import audit_legacy_history,quarantine_history_plan
from tennis_wc.ingestion.raw_response_store import utc_now


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--backup-dir')
    args=p.parse_args()
    db=Path(args.db).resolve()
    conn=sqlite3.connect(f'{db.as_uri()}?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    report=audit_legacy_history(conn)
    conn.close()
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if args.apply:
        if not args.backup_dir:
            p.error('--apply requires --backup-dir')
        folder=Path(args.backup_dir).resolve()
        if db.stat().st_size>1_000_000_000:
            mount=Path('/Volumes/Kelvin Hardisk 1')
            if not os.path.ismount(mount) or mount not in folder.parents:
                p.error('large DB backup requires the mounted external archive')
        folder.mkdir(parents=True,exist_ok=True)
        backup=folder/f"tennis-before-history-context-{utc_now().replace(':','').replace('-','')}.db"
        if backup.exists():
            p.error('backup already exists')
        source=sqlite3.connect(f'{db.as_uri()}?mode=ro',uri=True)
        target=sqlite3.connect(backup)
        try:
            source.backup(target)
            if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                raise RuntimeError('backup integrity failed')
        finally:
            source.close();target.close()
        with sqlite3.connect(db,timeout=30) as conn:
            conn.row_factory=sqlite3.Row
            conn.execute('BEGIN IMMEDIATE')
            report['quarantined']=quarantine_history_plan(conn,report,utc_now())
        report['backup']=str(backup)
        Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='cases'},ensure_ascii=False))


if __name__=='__main__':
    main()
