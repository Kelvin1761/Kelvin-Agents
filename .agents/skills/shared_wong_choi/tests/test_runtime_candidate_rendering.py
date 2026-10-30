"""Real render entrypoints in a miniature checkout; no native jobs or live data."""
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
FAMILIES = {
    'hkjc': ('.agents/skills/hkjc_racing/hkjc_daily_auto', 'bash'),
    'nba': ('.agents/skills/nba/nba_daily_auto', 'bash'),
    'tennis': ('tennis-wong-choi/scripts', 'zsh'),
    'central': ('.agents/skills/central_wong_choi', 'zsh'),
    'unified': ('.agents/skills/central_wong_choi', 'zsh'),
}


def tree_state(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode)
            for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('family', FAMILIES)
def test_candidate_render_uses_real_templates_without_runtime_side_effects(tmp_path, family):
    relative, shell = FAMILIES[family]
    repo = tmp_path / 'repo'
    skill = repo / relative
    skill.mkdir(parents=True)
    script = skill / ('install_production_runtime.sh' if family == 'unified'
                      else 'install_macos_launchd.sh')
    shutil.copyfile(ROOT / relative / script.name, script)
    if family == 'tennis':
        template_relative = 'tennis-wong-choi/launchd'
    else:
        template_relative = relative + '/launchd'
    shutil.copytree(ROOT / template_relative, repo / template_relative)
    if family in {'central', 'unified'}:
        shutil.copyfile(ROOT / relative / 'install_research_review.sh', skill / 'install_research_review.sh')
    if family == 'unified':
        shared = repo / '.agents/skills/shared_wong_choi'
        shared.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / '.agents/skills/shared_wong_choi/runtime_install_journal.sh',
                        shared / 'runtime_install_journal.sh')
        shutil.copyfile(ROOT / relative / 'install_macos_launchd.sh', skill / 'install_macos_launchd.sh')
        for name, (subrelative, _) in FAMILIES.items():
            if name in {'central', 'unified'}:
                continue
            subskill = repo / subrelative
            subskill.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / subrelative / 'install_macos_launchd.sh', subskill / 'install_macos_launchd.sh')
            subtemplates = ('tennis-wong-choi/launchd' if name == 'tennis'
                            else subrelative + '/launchd')
            shutil.copytree(ROOT / subtemplates, repo / subtemplates)
    home = tmp_path / 'home'
    home.mkdir()
    runtime = home / 'runtime'
    runtime.mkdir()
    (runtime / 'tennis_wc.db').write_bytes(b'fixture, never opened')
    (runtime / '.env').write_text('fixture, never sourced')
    python = runtime / 'python'
    python.write_text('#!/bin/sh\nexit 99\n')
    python.chmod(0o755)
    tools = tmp_path / 'bin'
    tools.mkdir()
    calls = tools / 'calls'
    launchctl = tools / 'launchctl'
    launchctl.write_text('#!/bin/sh\nprintf called >> "' + str(calls) + '"\nexit 99\n')
    launchctl.chmod(0o755)
    output = tmp_path / 'candidate'
    env = {**os.environ, 'HOME': str(home), 'PATH': str(tools) + ':' + os.environ['PATH'],
           'WC_TENNIS_RUNTIME_ROOT': str(runtime), 'TENNIS_PYTHON_BIN': str(python),
           'WC_INSTALL_RESEARCH_REVIEW': '1', 'WC_LAUNCHCTL_BIN': str(launchctl)}
    before_repo, before_home = tree_state(repo), tree_state(home)
    result = subprocess.run(['/bin/' + shell, str(script), '--render-only', str(output)],
                            env=env, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert not calls.exists(), 'candidate rendering must not call launchctl'
    assert tree_state(repo) == before_repo, 'render must not chmod scripts or write repo logs'
    assert tree_state(home) == before_home, 'render must not write runtime/config/evidence'
    assert not list(repo.rglob('logs')), 'render must not create log directories'
    assert not list(home.rglob('logs')), 'render must not create runtime log directories'
    templates = list(repo.rglob('*.plist.template'))
    expected = {p.name.removesuffix('.template') for p in templates}
    assert {p.name for p in output.iterdir()} == expected
    if family == 'unified':
        assert len(expected) == 20
    for p in output.iterdir():
        payload = plistlib.loads(p.read_bytes())
        assert payload['Label'] == p.stem
        assert '__' not in p.read_text()
        assert p.stat().st_mode & 0o777 == 0o644
