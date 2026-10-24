#!/usr/bin/env python3
"""Offline publication replay: immutable local cards, zero HTTP/deploy/scoring.

Copy/queue and real snapshot-build times are measured. Upload overlap uses an
explicit simulated delay; production logs measure actual Cloudflare costs.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import au_daily_schedule as S
import au_progressive_publish as P


def benchmark(data_root, base_snapshot, output, day, upload_delay=2.0, analysis_delay=.15):
    if shutil.disk_usage('/private/tmp').free < 10 * 1024**3:
        raise RuntimeError('less than 10 GiB free; do not start a replay')
    sources = []
    for folder in sorted(data_root.glob(f'{day} *')):
        snapshots = sorted((folder / '_prediction_snapshots').glob('*/manifest.json'))
        if snapshots:
            sources.append((folder.name, snapshots[-1].parent))
    if not sources:
        raise ValueError('no immutable meeting snapshots for requested date')
    report = {'day':day, 'meetings':len(sources), 'sportsbet_requests':0,
              'cloudflare_uploads':0, 'scoring_runs':0,
              'upload_simulation_seconds':upload_delay, 'analysis_simulation_seconds':analysis_delay,
              'source_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (Path(P.__file__), Path(S.__file__))},
              'base_snapshot_sha256':hashlib.sha256(base_snapshot.read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='au-publication-replay-', dir='/private/tmp') as scratch:
        root = Path(scratch)
        spool = root/'spool'
        queue = {'review_day':day, 'started_at':S.stamp(), 'archived':[], 'jobs':[]}
        P.atomic_json(spool/'queue.json', queue)
        batches = []
        errors = []
        copy_seconds = 0.0
        copy_bytes = 0
        first_publication = []

        def simulated_publish(log, folders, archived, **kwargs):
            batches.append(len(folders))
            time.sleep(upload_delay)
            if not first_publication:
                first_publication.append(time.monotonic())
            log.data['cloudflare_deployment'] = {'ok':True,'verified':{'ok':True},'simulation':True}
            log.data['dashboard_validation'] = {'ok':True}
            return True

        schedule = SimpleNamespace(RunLog=S.RunLog, step_dashboard=simulated_publish,
                                   reject_publication=S.reject_publication)

        def worker():
            try:
                P.run_worker(spool, schedule, poll_seconds=.01)
            except BaseException as exc:
                errors.append(str(exc))

        with patch.dict(os.environ, {'WC_AU_SCHED_LOG_DIR':str(root/'logs'),
                                      'WC_DASHBOARD_PUBLICATION_LOCK_PATH':str(root/'publish.lock')}):
            thread = threading.Thread(target=worker)
            started = time.monotonic()
            thread.start()
            try:
                for number, (name, source) in enumerate(sources, 1):
                    time.sleep(analysis_delay)
                    # One source copy at a time. Never copy an entire corpus or
                    # recursively copy nested prediction histories.
                    stage = root/'source'/name
                    stage.mkdir(parents=True)
                    for path in source.iterdir():
                        if path.is_file() and path.suffix in P.COPY_SUFFIXES:
                            shutil.copy2(path, stage/path.name)
                    target = spool/'inputs'/str(number)/name
                    t0 = time.monotonic()
                    digest, size = P.freeze_meeting(stage, target)
                    copy_seconds += time.monotonic()-t0
                    copy_bytes += size
                    if copy_bytes > P.MAX_QUEUE_BYTES:
                        raise ValueError('replay exceeds bounded publication queue')
                    shutil.rmtree(stage)
                    queue['jobs'].append({'id':str(number),'meeting':name,'folder':str(target),
                                          'digest':digest,'bytes':size,'queued_at':time.time()})
                    P.atomic_json(spool/'queue.json', queue)
                last_ready = time.monotonic()
            finally:
                (spool/'done').touch()
                thread.join(timeout=max(30,upload_delay*len(sources)+10))
            if thread.is_alive() or errors:
                raise RuntimeError(f'offline worker did not complete cleanly: {errors}')
            simulated = P.read_json(spool/'result.json')
            report.update(frozen_input_bytes=copy_bytes, foreground_copy_seconds=round(copy_seconds,4),
                          simulated_batches=batches, simulated_publish_count=len(batches),
                          simulated_first_live_before_last_ready=bool(first_publication and
                                                                     first_publication[0]<last_ready),
                          simulated_elapsed_seconds=round(time.monotonic()-started,4),
                          simulated_all_verified=simulated['complete'])
            before = {j['meeting']:P.meeting_digest(Path(j['folder'])) for j in queue['jobs']}
            log = S.RunLog('evening', date.fromisoformat(day), root/'build-log.json', notify=False)
            work = root/'real-build'
            work.mkdir()

            def cached_live(_log, destination):
                shutil.copy2(base_snapshot, destination)
                return destination

            with patch.object(S,'WORK_DIR',work), patch.object(S,'download_live_snapshot',cached_live):
                t0 = time.monotonic()
                ok = S.step_dashboard(log,[Path(j['folder']) for j in queue['jobs']],[],
                                      skip_deploy=True,recover_unpublished=False,
                                      isolate_failures=True,retain_intermediates=False)
                report['real_batch_build_seconds'] = round(time.monotonic()-t0,4)
            after = {j['meeting']:P.meeting_digest(Path(j['folder'])) for j in queue['jobs']}
            report['frozen_inputs_unchanged_by_real_builder'] = before == after
            report['real_build_passed'] = ok
            report['quarantined'] = log.data.get('publication_rejected',{})
            report['final_merge_json_files'] = len(list(work.glob('merge-*.json')))
            report['final_merge_html_files'] = len(list(work.glob('merge-*.html')))
            report['dashboard_meetings'] = (log.data.get('dashboard_validation') or {}).get('meetings')
            report['baseline_commit'] = subprocess.check_output(
                ['git','rev-parse','HEAD'],cwd=S.PROJECT_ROOT,text=True).strip()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--base-snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--day', required=True)
    parser.add_argument('--upload-delay', type=float, default=2.0)
    args = parser.parse_args()
    report = benchmark(args.data_root,args.base_snapshot,args.output,args.day,args.upload_delay)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['real_build_passed'] and report['frozen_inputs_unchanged_by_real_builder'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
