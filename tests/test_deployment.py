from contextlib import contextmanager
from pathlib import Path

import pytest

from api.deployment import https_url, server_issues
from scripts import migrate


@pytest.mark.parametrize('url', ['https://', 'http://api.photospot.app', 'https://user:secret@api.photospot.app',
                               'https://localhost', 'https://172.16.0.1', 'https://[::1]', 'https://api.local',
                               'https://api.example.com', 'https://api.photospot.app/#secret'])
def test_public_release_urls_reject_development_and_credentials(url):
    assert not https_url(url, public=True)


def test_cors_origin_cannot_contain_path_query_or_credentials():
    for url in ['https://api.photospot.app/path', 'https://api.photospot.app?q=1', 'https://x:y@api.photospot.app']:
        assert not https_url(url, origin=True)
    assert https_url('https://api.photospot.app', origin=True, public=True)


def test_server_reports_multiple_missing_fields_without_values():
    issues = server_issues({'JWT_SECRET': 'TOP-SECRET', 'DATABASE_URL': 'not-a-url-TOP-SECRET'}, growth=True)
    assert len(issues) >= 12
    assert 'TOP-SECRET' not in str(issues)


def test_complete_server_config_passes_without_external_requests():
    from cryptography.fernet import Fernet
    env = dict(APP_ENV='production', DEV_LOGIN='0', JWT_SECRET='random-fixture-secret-' * 3,
               DATABASE_URL='postgresql://app:fixture-strong-password@db/photospot',
               CORS_ORIGINS='https://photospot.app', GOOGLE_CLIENT_IDS='fixture-google',
               APPLE_AUDIENCES='app.photospot', APPLE_CLIENT_ID='app.photospot', APPLE_TEAM_ID='fixture-team',
               APPLE_KEY_ID='fixture-key', APPLE_PRIVATE_KEY_PATH='/mounted/apple.p8',
               APPLE_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode(),
               INSTAGRAM_CLIENT_ID='fixture-instagram', INSTAGRAM_CLIENT_SECRET='fixture-secret',
               INSTAGRAM_REDIRECT_URI='https://api.photospot.app/v1/social/instagram/callback',
               REVENUECAT_SECRET_KEY='fixture-revenuecat', OPENAI_API_KEY='fixture-openai')
    assert server_issues(env, growth=True) == []


class Connection:
    def __init__(self, *, applied=None, locked=False):
        self.applied = applied
        self.locked = locked
        self.sql = []
        self.rows = []
        self.transactions = 0

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield

    def execute(self, sql, params=()):
        self.sql.append((sql, params))
        if 'to_regclass' in sql:
            self.rows = [(None if self.applied is None else 'schema_migrations',)]
        elif 'SELECT name' in sql:
            self.rows = [(name,) for name in self.applied]
        elif 'pg_try_advisory_lock' in sql:
            self.rows = [(not self.locked,)]
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


def test_status_is_read_only_even_when_db_is_empty(monkeypatch):
    monkeypatch.setattr(migrate, 'files', lambda: [Path('schema.sql')])
    conn = Connection()
    assert migrate.run(conn, status=True, log=lambda _: None) == 1
    assert all(sql.startswith(('SELECT ', 'SET TRANSACTION READ ONLY')) for sql, _ in conn.sql)
    conn = Connection(applied={'schema.sql'})
    assert migrate.run(conn, status=True, log=lambda _: None) == 0


def test_deploy_cannot_seed_production_or_race_another_migration():
    conn = Connection(locked=True)
    with pytest.raises(ValueError, match='예시'):
        migrate.run(conn, seed=True, production=True)
    assert not conn.sql
    with pytest.raises(ValueError, match='다른 배포'):
        migrate.run(conn)
    assert len(conn.sql) == 1


def test_migrations_use_separate_transactions_and_release_lock(tmp_path, monkeypatch):
    files = []
    for i in range(2):
        path = tmp_path / f'{i}.sql'
        path.write_text(f'SELECT {i};', encoding='utf-8')
        files.append(path)
    monkeypatch.setattr(migrate, 'files', lambda: files)
    conn = Connection(applied=set())
    assert migrate.run(conn, log=lambda _: None) == 0
    assert conn.transactions == 2
    assert 'pg_advisory_unlock' in conn.sql[-1][0]
    assert [params[0] for sql, params in conn.sql if 'INSERT INTO' in sql] == ['0.sql', '1.sql']
