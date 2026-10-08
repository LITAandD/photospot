"""Comparable, sourced 2025 admissions. Missing counts are never zero visits.

Import explicitly reviewed public data; requests only read this local snapshot.
Rank across the active catalog, not the current radius or recommendation page.
"""
import argparse
import calendar
from collections import Counter
from datetime import date, datetime
import json
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from . import place_catalog as catalog

REFERENCE_YEAR = 2025


def today():
    return datetime.now(ZoneInfo('Asia/Seoul')).date()


def recent_months(as_of=None):
    as_of = as_of or today()
    month = as_of.year * 12 + as_of.month - 1
    return [f'{n // 12:04d}-{n % 12 + 1:02d}' for n in range(month - 3, month)]


def initialize(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS catalog_visitors (
        place_id TEXT NOT NULL, month TEXT NOT NULL, visitors INTEGER NOT NULL CHECK(visitors>=0),
        source_url TEXT NOT NULL, source_label TEXT NOT NULL, published_at TEXT NOT NULL,
        retrieved_at TEXT NOT NULL, count_basis TEXT NOT NULL CHECK(count_basis='admissions'),
        PRIMARY KEY(place_id,month))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS catalog_annual_visitors (
        place_id TEXT NOT NULL, year INTEGER NOT NULL, visitors INTEGER NOT NULL CHECK(visitors>=0),
        unit_id TEXT NOT NULL, unit_label TEXT NOT NULL,
        source_url TEXT NOT NULL, source_label TEXT NOT NULL, published_at TEXT NOT NULL,
        retrieved_at TEXT NOT NULL, count_basis TEXT NOT NULL CHECK(count_basis='admissions'),
        PRIMARY KEY(place_id,year), UNIQUE(unit_id,year))''')


def import_annual(records, path=None, as_of=None):
    """Reviewed exact venue mappings; one canonical catalog place per statistical unit."""
    as_of = as_of or today()
    checked, ids, units = [], set(), set()
    with catalog.connect(path) as conn:
        initialize(conn)
        known = {r['id']: dict(r) for r in conn.execute('SELECT * FROM places')}
        for row in records:
            pid, year, count = row['place_id'], row['year'], row['visitors']
            url = urlsplit(row['source_url'])
            published = date.fromisoformat(row['published_at'])
            unit = row['unit_id']
            if (type(year) is not int or year != REFERENCE_YEAR or pid not in known
                    or row['place_source'] != known[pid]['source_url']
                    or row['place_name'] != known[pid]['name']
                    or type(count) is not int or count < 0 or (pid, year) in ids or (unit, year) in units
                    or not unit.strip() or not row['unit_label'].strip()
                    or not date(year + 1, 1, 1) <= published <= as_of
                    or url.scheme != 'https' or not url.hostname or url.username or url.password
                    or row.get('count_basis') != 'admissions' or not row['source_label'].strip()):
                raise ValueError('Invalid annual admissions or venue mapping')
            existing = conn.execute('SELECT place_id FROM catalog_annual_visitors WHERE unit_id=? AND year=?', (unit, year)).fetchone()
            if existing and existing[0] != pid:
                raise ValueError('Statistical unit already mapped to another place')
            ids.add((pid, year)); units.add((unit, year))
            checked.append((pid, year, count, unit, row['unit_label'], row['source_url'],
                            row['source_label'], published.isoformat(), as_of.isoformat(), 'admissions'))
        conn.executemany('INSERT OR REPLACE INTO catalog_annual_visitors VALUES (?,?,?,?,?,?,?,?,?,?)', checked)
    return len(checked)


def import_records(records, path=None, as_of=None):
    """Only complete monthly place-level admissions, never reviews/search/area footfall.

The file is a reviewed mapping to exact catalog IDs. Ambiguous names and venue
groups must be resolved before import. Validate the entire batch before writing.
"""
    as_of = as_of or today()
    checked, keys = [], set()
    with catalog.connect(path) as conn:
        initialize(conn)
        known = {r[0] for r in conn.execute('SELECT id FROM places')}
        for row in records:
            pid, month, count = row['place_id'], row['month'], row['visitors']
            start = date.fromisoformat(month + '-01')
            end = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
            published = date.fromisoformat(row['published_at'])
            url = urlsplit(row['source_url'])
            if (pid not in known or type(count) is not int or count < 0 or month != start.strftime('%Y-%m')
                    or end >= as_of or not end <= published <= as_of or (pid, month) in keys
                    or url.scheme != 'https' or not url.hostname or url.username or url.password
                    or row.get('count_basis') != 'admissions' or not row['source_label'].strip()):
                raise ValueError('Invalid or incomparable visitor record')
            keys.add((pid, month))
            checked.append((pid, month, count, row['source_url'], row['source_label'],
                            published.isoformat(), as_of.isoformat(), 'admissions'))
        conn.executemany('INSERT OR REPLACE INTO catalog_visitors VALUES (?,?,?,?,?,?,?,?)', checked)
    return len(checked)


def rankings(path=None, as_of=None):
    as_of = as_of or today()
    months = [f'{REFERENCE_YEAR}-{m:02d}' for m in range(1, 13)]
    with catalog.connect(path) as conn:
        initialize(conn)
        catalog_count = conn.execute('SELECT count(*) FROM places WHERE active=1').fetchone()[0]
        rows = conn.execute('''SELECT v.* FROM catalog_visitors v JOIN places p ON p.id=v.place_id
            WHERE p.active=1 AND v.month IN (?,?,?,?,?,?,?,?,?,?,?,?) AND v.published_at<=? AND v.count_basis='admissions'
            ORDER BY v.month''', (*months, as_of.isoformat())).fetchall()
        annual = conn.execute('''SELECT v.* FROM catalog_annual_visitors v JOIN places p ON p.id=v.place_id
            WHERE p.active=1 AND v.year=? AND v.published_at<=?''', (REFERENCE_YEAR, as_of.isoformat())).fetchall()
    grouped = {}
    for row in rows:
        grouped.setdefault(row['place_id'], []).append(dict(row))
    complete = {pid: entries for pid, entries in grouped.items() if {e['month'] for e in entries} == set(months)}
    totals = {pid: sum(e['visitors'] for e in entries) for pid, entries in complete.items()}
    # An official annual total takes precedence over a monthly reconstruction.
    for row in annual:
        totals[row['place_id']] = row['visitors']
        complete[row['place_id']] = [dict(row)]
    n = len(totals)
    context = {'period_start': months[0], 'period_end': months[-1], 'as_of': as_of.isoformat(),
               'catalog_count': catalog_count, 'measured_count': n, 'status': 'unavailable',
               'rank': None, 'visitors': None, 'percentile': None, 'sources': []}
    result = {}
    counts, below, cumulative = Counter(totals.values()), {}, 0
    for total in sorted(counts):
        below[total] = cumulative
        cumulative += counts[total]
    for pid, total in totals.items():
        lower, equal = below[total], counts[total]
        percentile = (lower + (equal - 1) / 2) / (n - 1) if n > 1 else None
        result[pid] = {**context, 'status': 'ranked' if n > 1 else 'insufficient',
                       'visitors': total, 'rank': 1 + n - lower - equal,
                       'unit_label': complete[pid][0].get('unit_label'),
                       'percentile': percentile,
                       'sources': list({e['source_url']: {'url': e['source_url'], 'label': e['source_label']}
                                        for e in complete[pid]}.values())}
    return context, result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path, help='Reviewed JSON array of monthly admissions records')
    parser.add_argument('--annual', action='store_true', help='Import reviewed 2025 annual totals')
    args = parser.parse_args()
    importer = import_annual if args.annual else import_records
    print('Imported visitor records:', importer(json.loads(args.file.read_text(encoding='utf-8'))))
