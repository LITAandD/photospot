"""Run the Python blocks shipped in the actual scheduled workflow."""
from datetime import datetime
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import yaml

WORKFLOW = yaml.safe_load((Path(__file__).resolve().parents[1] / '.github/workflows/data-refresh.yml').read_text('utf-8'))


def block(step):
    return step['run'].split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]


@pytest.mark.parametrize('scenario,skip', [
    ('complete', True), ('manual-success', False), ('partial', False), ('all-failed', False),
    ('unstarted', False), ('running', False), ('previous-day', False), ('future-day', False),
    ('self', False), ('other-branch', False), ('api-error', False), ('malformed', False),
    ('missing-proof', False), ('primary', False), ('manual-trigger', False),
])
def test_actual_schedule_gate(tmp_path, monkeypatch, scenario, skip):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 18, 7, 17, tzinfo=tz)
    monkeypatch.setattr('datetime.datetime', Clock)
    env = dict(GITHUB_REPOSITORY='example/repo', GITHUB_RUN_NUMBER='10',
               GITHUB_EVENT_NAME='workflow_dispatch' if scenario == 'manual-trigger' else 'schedule',
               CRON='0 22 * * *' if scenario == 'primary' else '17 22 * * *',
               GITHUB_OUTPUT=str(tmp_path / 'output'), GITHUB_STEP_SUMMARY=str(tmp_path / 'summary'))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    run = dict(id=99, run_number=9, event='schedule', head_branch='main',
               created_at='2026-11-17T22:00:00Z', conclusion='success')
    if scenario == 'manual-success':
        run['event'] = 'workflow_dispatch'
    if scenario == 'previous-day':
        run['created_at'] = '2026-11-17T14:59:59Z'
    if scenario == 'future-day':
        run['created_at'] = '2026-11-18T15:00:00Z'
    if scenario == 'self':
        run['run_number'] = 10
    if scenario == 'other-branch':
        run['head_branch'] = 'candidate'
    if scenario == 'running':
        run['conclusion'] = None
    if scenario == 'all-failed':
        run['conclusion'] = 'failure'
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if scenario == 'api-error':
            raise subprocess.CalledProcessError(1, args)
        if scenario == 'malformed':
            return SimpleNamespace(stdout='{}')
        if args[4].endswith('/runs'):
            return SimpleNamespace(stdout=json.dumps({'workflow_runs': [] if scenario == 'unstarted' else [run]}))
        proof = dict(name='Confirm complete collection', conclusion='failure' if scenario == 'partial' else 'success')
        return SimpleNamespace(stdout=json.dumps({'jobs': [
            dict(name='refresh', conclusion='success', steps=[] if scenario == 'missing-proof' else [proof])
        ]}))
    monkeypatch.setattr(subprocess, 'run', command)
    exec(compile(block(WORKFLOW['jobs']['schedule-gate']['steps'][0]), 'schedule-gate', 'exec'), {})
    assert (tmp_path / 'output').read_text().strip() == 'run-refresh=' + ('false' if skip else 'true')
    if scenario in {'primary', 'manual-trigger'}:
        assert not calls


@pytest.mark.parametrize('status,updated,failures,unattempted', [
    ('complete', 3, [], 0), ('partial', 2, [{'error': 'HTTP 500'}], 0),
    ('partial', 1, [], 2), ('failed', 0, [{'error': 'HTTP 403'}], 2),
])
def test_collection_completion_is_explicit(tmp_path, monkeypatch, status, updated, failures, unattempted):
    monkeypatch.chdir(tmp_path)
    report = dict(status=status, candidates=3, attempted=3-unattempted, updated=updated,
                  unattempted=unattempted, failures=failures, stopped=None)
    Path('artifacts').mkdir()
    Path('artifacts/official-hours-import.json').write_text(json.dumps(report))
    steps = WORKFLOW['jobs']['refresh']['steps']
    proof = steps[-1]
    assert proof['name'] == 'Confirm complete collection'
    assert steps[-2]['name'] == 'Verify changed files and publish review PR'
    if status == 'complete':
        exec(compile(block(proof), 'completion', 'exec'), {})
    else:
        with pytest.raises(SystemExit):
            exec(compile(block(proof), 'completion', 'exec'), {})
