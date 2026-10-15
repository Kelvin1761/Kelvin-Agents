"""Read-only production-engine dump at a preregistered trial cutoff."""
from pathlib import Path
import runpy
import sys

scripts = Path(__file__).resolve().parents[1] / '.agents/skills/au_racing/au_wong_choi_auto/scripts'
sys.path.insert(0, str(scripts))
from au_racing_engine import engine_core  # noqa: E402

cutoff, output = int(sys.argv[1]), sys.argv[2]
assert cutoff in (2, 4, 6)
engine_core.TRIAL_PERFORMANCE_START_CUTOFF = cutoff
sys.argv = ['au_dump_engine_leaves.py', '--out', output]
runpy.run_path(str(scripts / 'au_dump_engine_leaves.py'), run_name='__main__')
