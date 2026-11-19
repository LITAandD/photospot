"""Local operator command. Never expose a new public admin secret or endpoint."""
import argparse
import html
from pathlib import Path

from . import visitor_photos as store


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('migrate')
    queue = sub.add_parser('queue')
    queue.add_argument('--output', type=Path, required=True)
    review = sub.add_parser('review')
    review.add_argument('id')
    review.add_argument('--sha256', required=True)
    review.add_argument('--reviewer', required=True)
    review.add_argument('--decision', choices=['approve', 'reject'], required=True)
    review.add_argument('--note', default='')
    for check in ['place', 'rights', 'faces', 'scene']:
        review.add_argument('--' + check + '-confirmed', action='store_true')
    prune = sub.add_parser('prune')
    prune.add_argument('--apply', action='store_true')
    args = p.parse_args()
    if args.command == 'migrate':
        store.migrate()
        print('Visitor photo schema ready; catalog untouched')
    elif args.command == 'review':
        store.review(args.id, args.sha256, args.reviewer, args.decision, args.note,
                     {k: getattr(args, k + '_confirmed') for k in ['place', 'rights', 'faces', 'scene']})
        print('Review saved')
    elif args.command == 'prune':
        with store.connection() as conn:
            store.lock(conn)
            count = conn.execute('SELECT count(*) AS n FROM visitor_photos WHERE expires_at<=%s', (store.stamp(),)).fetchone()['n']
            if args.apply:
                conn.execute('DELETE FROM visitor_photos WHERE expires_at<=%s', (store.stamp(),))
        print(f'Expired: {count}; deleted: {bool(args.apply)}')
    else:
        # Only blurred, metadata-free files. Treat this review bundle as private.
        args.output.mkdir(parents=True, exist_ok=True)
        with store.connection() as conn:
            rows = conn.execute("SELECT * FROM visitor_photos WHERE state='pending' AND expires_at>%s ORDER BY created_at LIMIT 50",
                                (store.stamp(),)).fetchall()
        content = ['<!doctype html><meta charset="utf-8"><title>비공개 사진 검수</title>',
                   '<meta http-equiv="Content-Security-Policy" content="default-src &apos;none&apos;; img-src &apos;self&apos;">',
                   '<h1>비공개 · 사용자 촬영 예시 검수</h1><p>얼굴·반사된 얼굴·타인·위치·권리·구도를 직접 확인하세요. 자동 승인하지 않습니다.</p>']
        for row in rows:
            image = args.output / (row['id'] + '.jpg')
            image.write_bytes(bytes(row['image']))
            fields = {k: row[k] for k in ['id', 'place_id', 'image_sha256', 'credit', 'caption', 'consent', 'faces']}
            content.append('<section><h2>' + html.escape(row['credit']) + '</h2><img width="640" src="' + image.name
                           + '" alt="블러 처리된 검수 후보"><pre>' + html.escape(str(fields)) + '</pre></section>')
        (args.output / 'review.html').write_text('\n'.join(content), encoding='utf-8')
        print(f'Private review bundle: {len(rows)} candidates. Delete this local bundle after review.')


if __name__ == '__main__':
    main()

