"""Exercise the scheduled collector and its actual Git publication boundary without network access."""
from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from pipeline import official_place_hours as hours
from scripts import official_hours_pr as review


@pytest.mark.parametrize(('unavailable', 'status', 'updated'), [
    (set(), 'complete', 3), ({'9990'}, 'partial', 2),
    (set(hours.DAILY_STORES.values()), 'failed', 0), ({'rate-limit'}, 'failed', 0),
])
def test_daily_targets_and_retention(tmp_path, monkeypatch, unavailable, status, updated):
    class Clock(datetime):
        @classmethod
        def now(cls, tz):
            return cls(2026, 10, 8, 7, tzinfo=tz)
    monkeypatch.setattr(hours, 'datetime', Clock)
    today = Clock.now(hours.ZoneInfo('Asia/Seoul')).date()
    previous = (today - timedelta(days=1)).isoformat()
    rows = [dict(place_id=pid, store_id=sid, branch=f'스타벅스 테스트{sid}', lat=37.5, lng=127,
                 address='테스트로 10') for pid, sid in hours.DAILY_STORES.items()]
    rows.append(dict(rows[0], place_id='other-place', store_id='1000'))
    for row in rows:
        row.update(checked_at=previous, date_hours={previous: '10:00–18:00'})
    stores = {row['store_id']: row for row in rows}
    places = [dict(id=r['place_id'], category='cafe', name=r['branch'], lat=r['lat'], lng=r['lng'],
                   address=r['address']) for r in rows]
    @contextmanager
    def connect():
        yield SimpleNamespace(execute=lambda sql: places)
    calls = []
    def post(self, action, params):
        sid = params['in_biz_cd']
        calls.append(sid)
        if 'rate-limit' in unavailable:
            raise HTTPError('https://example.com', 429, 'test', {}, None)
        if sid in unavailable:
            raise OSError('Unavailable')
        row = stores[sid]
        if action == 'getStoreView':
            return {'view': [dict(s_biz_code=sid, s_name=row['branch'].removeprefix('스타벅스 '),
                                  lat=row['lat'], lot=row['lng'], doro_address=row['address'])]}
        assert action == 'getStoreTime'
        return {'list': [dict(store_time_day=today.day, store_time_week=(today.weekday()+1) % 7+1,
                              store_opentime='0930-1800', store_time_hlytag='1')]}
    path = tmp_path / 'hours.json'
    path.write_text(json.dumps(rows), encoding='utf-8')
    before = path.read_bytes()
    monkeypatch.setattr(hours.catalog, 'ROOT', tmp_path)
    monkeypatch.setattr(hours.catalog, 'connect', connect)
    monkeypatch.setattr(hours.official.Client, 'post', post)
    monkeypatch.setattr(hours, 'DATA', path)
    hours.entries.cache_clear()
    try:
        report = hours.run(daily=True)
        assert (report['status'], report['updated'], report['candidates']) == (status, updated, 3)
        assert set(calls) <= set(hours.DAILY_STORES.values())
        if 'rate-limit' in unavailable:
            assert len(calls) == 1 and report['unattempted'] == 2
        if not updated:
            assert before == path.read_bytes()
        after = json.loads(path.read_text(encoding='utf-8'))
        for old, new in zip(rows, after, strict=True):
            if old['store_id'] in unavailable or old['place_id'] not in hours.DAILY_STORES or not updated:
                assert new == old
            else:
                assert new == dict(old, checked_at=today.isoformat(), date_hours={today.isoformat(): '09:30–18:00'})
        saved = path.read_bytes()
        hours.run(daily=True)
        assert path.read_bytes() == saved
    finally:
        hours.entries.cache_clear()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def set_review_hours(day):
    write_json(review.HOURS, [dict(place_id=pid, store_id=store, checked_at=day, date_hours={day: '09:00–18:00'})
                             for pid, store in hours.DAILY_STORES.items()])
    refresh_manifest()


def refresh_manifest():
    digest = hashlib.sha256(Path(review.HOURS).read_bytes()).hexdigest()
    write_json(review.MANIFEST, {'sha256': hashlib.sha256(b'original snapshot').hexdigest(),
                                 'pipeline_data_sha256': {'official_place_hours.json': digest}})


@pytest.fixture
def repo(tmp_path, monkeypatch):
    origin = tmp_path / 'origin.git'
    repo = tmp_path / 'checkout'
    repo.mkdir()
    monkeypatch.chdir(repo)
    monkeypatch.setenv('GITHUB_REPOSITORY', 'test/photospot')
    monkeypatch.setenv('GITHUB_RUN_ID', '123')
    git = review.command
    git('git', 'init', '--bare', str(origin))
    git('git', 'init', '-b', 'main')
    git('git', 'config', 'user.email', 'test@example.org')
    git('git', 'config', 'user.name', 'Test')
    git('git', 'remote', 'add', 'origin', str(origin))
    Path('.gitignore').write_text('artifacts/\n')
    Path('catalog').mkdir()
    Path('catalog/places.sqlite3').write_bytes(b'original snapshot')
    set_review_hours('2026-01-01')
    git('git', 'add', '.')
    git('git', 'commit', '-m', 'base')
    git('git', 'push', 'origin', 'main')
    git('git', 'checkout', '--detach')
    write_json('artifacts/official-hours-import.json', dict(checked_at='2026-01-02', updated=3, failures=[], unattempted=0))
    class Actions(list):
        body = 'Reviewer notes: preserve this paragraph.'
        closed = False
        fail_create = False
    actions = Actions()
    def run(*args):
        if args[0] != 'gh':
            return git(*args)
        if '--method' in args and 'GET' in args:
            if args[args.index('GET')+1].endswith('/pulls/42'):
                return json.dumps({'body': actions.body})
            if 'state=closed' in args:
                return '[{"number":42}]' if actions.closed else '[]'
            return '[{"number":42}]' if 'create' in actions and not actions.closed else '[]'
        if args[1:3] == ('pr', 'create'):
            assert '--draft' in args and args[args.index('--base')+1] == 'main'
            if actions.fail_create:
                raise RuntimeError('PR creation unavailable')
            actions.append('create')
            return 'https://example.com/pull/42'
        assert 'PATCH' in args and 'repos/test/photospot/pulls/42' in args
        actions.body = next(a[5:] for a in args if a.startswith('body='))
        actions.append('update')
        return ''
    monkeypatch.setattr(review, 'command', run)
    return actions


def test_refresh_review_lifecycle(repo):
    git = review.command
    base = git('git', 'rev-parse', 'HEAD')
    state = review.prepare()
    assert '변경 없음' in review.publish(state) and not repo
    set_review_hours('2026-01-02')
    review.publish(state)
    assert repo == ['create']
    tip = git('git', 'rev-parse', 'HEAD')
    assert git('git', 'diff', '--name-only', base, tip).splitlines() == [review.MANIFEST, review.HOURS]
    git('git', 'checkout', '--detach', base)
    state = review.prepare()
    assert state == {'tip': tip, 'pr': 42}
    assert json.loads(Path(review.HOURS).read_text())[0]['checked_at'] == '2026-01-02'
    set_review_hours('2026-01-02')  # same pending hours, including regenerated manifest
    assert '변경 없음' in review.publish(state)
    assert repo == ['create']
    set_review_hours('2026-01-03')
    review.publish(state)
    assert repo == ['create', 'update']
    assert repo.body.startswith('Reviewer notes: preserve this paragraph.')
    assert repo.body.count(review.AUTO_BEGIN) == repo.body.count(review.AUTO_END) == 1
    assert git('git', 'ls-remote', 'origin', 'refs/heads/main').split()[0] == base


@pytest.mark.parametrize('unexpected', ['untracked-photo.jpg', 'unstaged-db', 'staged-db', 'manifest', 'other-store'])
def test_unexpected_changes_block_push(repo, unexpected):
    state = review.prepare()
    set_review_hours('2026-01-02')
    if unexpected == 'manifest':
        write_json(review.MANIFEST, {'sha256': 'different snapshot'})
    elif unexpected == 'other-store':
        rows = json.loads(Path(review.HOURS).read_text())
        write_json(review.HOURS, rows + [dict(rows[0], place_id='other')])
    elif unexpected.endswith('-db'):
        Path('catalog/places.sqlite3').write_bytes(b'modified snapshot')
        if unexpected == 'staged-db':
            subprocess.run(['git', 'add', 'catalog/places.sqlite3'], check=True)
    else:
        Path(unexpected).write_bytes(b'photo')
    with pytest.raises(ValueError):
        review.publish(state)
    assert not repo and not review.command('git', 'ls-remote', 'origin', review.REF)


def test_orphan_push_is_carried_forward_before_partial_collection(repo):
    git = review.command
    base = git('git', 'rev-parse', 'HEAD')
    state = review.prepare()
    set_review_hours('2026-01-02')
    repo.fail_create = True
    with pytest.raises(RuntimeError, match='creation unavailable'):
        review.publish(state)
    previous = json.loads(Path(review.HOURS).read_text())
    git('git', 'checkout', '--detach', base)
    repo.fail_create = False
    state = review.prepare()
    assert state['pr'] is None and state['tip']
    assert json.loads(Path(review.HOURS).read_text()) == previous
    # Tomorrow only one store succeeds; the two unavailable stores keep yesterday's success.
    rows = json.loads(Path(review.HOURS).read_text())
    rows[0].update(checked_at='2026-01-03', date_hours={'2026-01-03': '10:00–20:00'})
    write_json(review.HOURS, rows)
    refresh_manifest()
    review.publish(state)
    assert repo == ['create']
    published = json.loads(git('git', 'show', f'HEAD:{review.HOURS}'))
    assert published[1:] == previous[1:]
    assert git('git', 'ls-remote', 'origin', 'refs/heads/main').split()[0] == base


def test_closed_review_is_not_resurrected(repo):
    git = review.command
    base = git('git', 'rev-parse', 'HEAD')
    state = review.prepare()
    set_review_hours('2026-01-02')
    review.publish(state)
    repo.closed = True
    git('git', 'checkout', '--detach', base)
    state = review.prepare()
    assert state['pr'] is None
    assert all(r['checked_at'] == '2026-01-01' for r in json.loads(Path(review.HOURS).read_text()))
    assert '변경 없음' in review.publish(state)
    assert repo == ['create']


def test_prepare_conflict_is_actionable_and_does_not_push(repo, capsys):
    git = review.command
    base = git('git', 'rev-parse', 'HEAD')
    state = review.prepare()
    set_review_hours('2026-01-02')
    review.publish(state)
    tip = git('git', 'ls-remote', 'origin', review.REF)
    git('git', 'checkout', '--detach', base)
    set_review_hours('2026-01-03')
    git('git', 'add', '.')
    git('git', 'commit', '-m', 'concurrent main hours')
    with pytest.raises(SystemExit) as error:
        review.prepare()
    assert error.value.code == 1 and '::error title=운영시간 검토 브랜치 충돌' in capsys.readouterr().out
    assert git('git', 'ls-remote', 'origin', review.REF) == tip


def test_automated_body_replaces_only_its_block():
    old = f'Reviewer before\n{review.AUTO_BEGIN}\nold\n{review.AUTO_END}\nReviewer after'
    updated = review.review_body(old, 'new report')
    assert updated == old.replace('\nold\n', '\nnew report\n')
    assert review.review_body(updated, 'new report') == updated
    with pytest.raises(ValueError):
        review.review_body(review.AUTO_BEGIN + review.AUTO_BEGIN, 'report')


def test_daily_store_identity_matches_reviewed_source():
    records = json.loads(hours.DATA.read_text(encoding='utf-8'))
    assert {r['place_id']: r['store_id'] for r in records if r['place_id'] in hours.DAILY_STORES} == hours.DAILY_STORES
