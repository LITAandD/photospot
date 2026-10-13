"""Stable public photo identity, independent of thumbnail size and place ranking."""
import hashlib
from urllib.parse import unquote, urlsplit


def source_key(source_url):
    """Only a Commons file page identifies one asset across thumbnail sizes."""
    try:
        parsed = urlsplit(source_url)
    except ValueError:
        return None
    if parsed.hostname == 'commons.wikimedia.org' and parsed.path.startswith('/wiki/File:'):
        return 'commons:' + unquote(parsed.path[len('/wiki/File:'):]).replace('_', ' ')
    # Other source pages may contain multiple unrelated photos.
    return None


def photo_id(photo):
    return hashlib.sha256(((photo.get('source_url') or '') + '\n' +
                           (photo.get('original_url') or photo['url'])).encode()).hexdigest()
