"""Validate incremental NBA result timing before any launchd cutover."""
import plistlib
from pathlib import Path
import sys


def verify(path):
    data = plistlib.loads(Path(path).read_bytes())
    if data.get('StartInterval') != 900:
        raise ValueError('NBA results local timer must be 900 seconds; external calls remain source-time gated')
    if '--incremental-results' not in data.get('ProgramArguments', []):
        raise ValueError('NBA results timer must use incremental source-time checks')
    slots = {(row.get('Hour'), row.get('Minute')) for row in data.get('StartCalendarInterval', [])}
    if slots != {(18, 30), (21, 30)}:
        raise ValueError('Preserve only the existing 18:30/21:30 nightly archive slots')


if __name__ == '__main__':
    verify(sys.argv[1])
