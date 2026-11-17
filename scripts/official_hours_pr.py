"""Prepare or publish the dedicated official-hours review branch from a clean main checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from pipeline.official_place_hours import DAILY_STORES

HOURS = 'pipeline/data/official_place_hours.json'
MANIFEST = 'catalog/places.manifest.json'
BRANCH = 'data-refresh/official-hours'
REF = f'refs/heads/{BRANCH}'


def command(*args):
    return subprocess.check_output(args, encoding='utf-8').strip()


def open_review():
    repo = os.environ['GITHUB_REPOSITORY']
    pulls = json.loads(command('gh', 'api', '--method', 'GET', f'repos/{repo}/pulls',
                               '-f', 'state=open', '-f', 'base=main', '-f', f'head={repo.split("/")[0]}:{BRANCH}'))
    return pulls[0]['number'] if pulls else None


def prepare():
    # checkout fetch-depth: 0 includes the existing review ref (also if PR creation failed yesterday).
    tip = command('git', 'for-each-ref', '--format=%(objectname)', f'refs/remotes/origin/{BRANCH}')
    pr = open_review()
    if pr:
        if not tip:
            raise ValueError('Open hours PR has no fetched branch')
        diff = ('git', 'diff', f'HEAD...{tip}')
        subprocess.run([*diff, '--exit-code', '--', '.', f':(exclude){HOURS}', f':(exclude){MANIFEST}'], check=True)
        patch = subprocess.check_output([*diff, '--binary', '--full-index', '--', HOURS])
        if patch:
            # Carry forward a pending success if today's collection fails for that store.
            # Concurrent main edits to the same hours must be resolved by a reviewer.
            subprocess.run(['git', 'apply', '--3way'], input=patch, check=True)
    return {'tip': tip, 'pr': pr}


def validate_changes():
    status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--no-renames', '-z', '-uall'])
    for entry in status.decode('utf-8').split('\0'):
        if entry and (entry[:2] not in {' M', 'M ', 'MM'} or entry[3:] not in {HOURS, MANIFEST}):
            raise ValueError(f'Unexpected file change before push: {entry!r}')
    before = json.loads(command('git', 'show', f'HEAD:{HOURS}'))
    after = json.loads(Path(HOURS).read_text(encoding='utf-8'))
    if len(before) != len(after):
        raise ValueError('Official hours records added or removed')
    for old, new in zip(before, after):
        if old == new:
            continue
        if (DAILY_STORES.get(old['place_id']) != old['store_id']
                or old.keys() != new.keys()
                or any(old[k] != new[k] for k in old.keys() - {'date_hours', 'checked_at'})
                or new['checked_at'] < old['checked_at']):
            raise ValueError('Out-of-scope or older official hours')
    expected = json.loads(command('git', 'show', f'HEAD:{MANIFEST}'))
    with Path('catalog/places.sqlite3').open('rb') as snapshot:
        if hashlib.file_digest(snapshot, 'sha256').hexdigest() != expected['sha256']:
            raise ValueError('SQLite snapshot hash differs from the main manifest')
    checksum = hashlib.sha256(Path(HOURS).read_text(encoding='utf-8').encode()).hexdigest()
    expected['pipeline_data_sha256'][Path(HOURS).name] = checksum
    if json.loads(Path(MANIFEST).read_text(encoding='utf-8')) != expected:
        raise ValueError('Manifest differs outside the official hours checksum or has the wrong checksum')


def publish(state):
    validate_changes()
    subprocess.run(['git', 'add', '--', HOURS, MANIFEST], check=True)
    tree = command('git', 'write-tree')
    if tree == command('git', 'rev-parse', 'HEAD^{tree}'):
        return '변경 없음 · 새 PR 없음'
    if command('git', 'rev-parse', f'HEAD:{HOURS}') == command('git', 'rev-parse', f':{HOURS}'):
        raise ValueError('Manifest changed without new official hours')
    refs = command('git', 'ls-remote', 'origin', 'refs/heads/main', REF)
    remote = {ref: sha for sha, ref in (line.split() for line in refs.splitlines())}
    tip, pr = state['tip'], state['pr']
    if (remote.get('refs/heads/main') != command('git', 'rev-parse', 'HEAD')
            or remote.get(REF, '') != tip or open_review() != pr):
        raise ValueError('main or the hours review changed during collection; rerun from main')
    if (not tip or tree != command('git', 'rev-parse', f'{tip}^{{tree}}')
            or command('git', 'merge-base', 'HEAD', tip) != command('git', 'rev-parse', 'HEAD')):
        command('git', '-c', 'user.name=github-actions[bot]',
                '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                'commit', '-m', 'data: 스타벅스 3개 지점 공식 운영시간 갱신')
        command('git', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential',
                'push', f'--force-with-lease={REF}:{tip}', 'origin', f'HEAD:{REF}')
    elif pr:
        return f'변경 없음 · 기존 PR #{pr} 유지'
    report = json.loads(Path('artifacts/official-hours-import.json').read_text(encoding='utf-8'))
    repo = os.environ['GITHUB_REPOSITORY']
    run = f"https://github.com/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    body = (f"{report['checked_at']} 공식 시간표 확인. 성공 {report['updated']}곳, 실패 {len(report['failures'])}곳, "
            f"미시도 {report['unattempted']}곳. 실패 지점의 기존 기록을 보존합니다.\n\n[수집 보고서]({run})")
    if pr:
        command('gh', 'api', '--method', 'PATCH', f'repos/{repo}/pulls/{pr}', '-f', f'body={body}', '--silent')
        return f'기존 PR #{pr} 갱신'
    url = command('gh', 'pr', 'create', '--repo', repo, '--base', 'main', '--head', BRANCH,
                  '--draft', '--title', 'data: 스타벅스 3개 지점 공식 운영시간 갱신', '--body', body)
    return f'검토용 PR 생성 · {url}'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=['prepare', 'publish'])
    args = parser.parse_args()
    state_file = Path(os.environ['RUNNER_TEMP']) / 'official-hours-review.json'
    if args.step == 'prepare':
        state_file.write_text(json.dumps(prepare()), encoding='utf-8')
    else:
        result = publish(json.loads(state_file.read_text(encoding='utf-8')))
        print(result)
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
            print(result, file=summary)
