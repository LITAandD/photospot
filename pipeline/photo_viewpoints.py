"""Exclude reviewed bird views and explicit aerial-photo metadata before ranking.

Unknown viewpoints remain eligible; panoramas, skylines, birds and aircraft as
subjects do not establish the camera angle. Reviews identify images, not venues.
No photo downloads or network inference runs in a recommendation request.
"""
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .photo_identity import source_key

REVIEWS = json.loads((Path(__file__).parent / 'data/photo_viewpoint_reviews.json').read_text(encoding='utf-8'))['photos']
BLOCKED_URLS = {r['photo_url'] for r in REVIEWS if r['viewpoint'] == 'bird_view'}
BLOCKED_SOURCES = {key for r in REVIEWS if r['viewpoint'] == 'bird_view' and (key := source_key(r['source_url']))}

AIR_VIEW = re.compile(
    r"\b(?:aerial[\s-]+(?:view|photo\w*|shot|image|panorama|footage)|"
    r"bird(?:['’]s|s)?[\s-]*(?:eye[\s-]*view|view)|"
    r"drone[\s-]+(?:view|photo\w*|shot|image|footage)|"
    r"(?:view|photo\w*|shot|image)[^.!?\n]{0,50}\bfrom\b[^.!?\n]{0,20}\b(?:helicopter|airplane|drone)|"
    r"from[\s-]+the[\s-]+view[\s-]+of[\s-]+a[\s-]+helicopter|"
    r"(?:overhead|top[\s-]*down)[\s-]+(?:view|photo\w*|shot)|view[\s-]+from[\s-]+above)\b"
    r"|조감(?:도|뷰|사진|촬영)?|부감[\s-]*(?:뷰|사진|촬영)|버드[\s-]*(?:아이[\s-]*)?뷰"
    r"|(?:항공|드론)[\s-]*(?:촬영|사진|뷰|샷)", re.I)
TOWER_VIEW = re.compile(
    r'\b(?:view|seen|looking|cityscape|skyline|city core|park|river)'
    r'[^.!?\n]{0,70}\bfrom\s+(?!(?:the\s+)?(?:left|right|front|base|foot|outside|near|entrance)\b)'
    r'[^;,:.!?\n]{0,60}\b(?:tower|observation deck)\b', re.I)


def bird_view(photo_url='', source_url='', title='', description=''):
    if photo_url in BLOCKED_URLS or source_key(source_url) in BLOCKED_SOURCES:
        return True
    # Decode filenames, never URL query strings or a venue's descriptive tags.
    try:
        filenames = ' '.join(unquote(urlsplit(url).path.rsplit('/', 1)[-1]) for url in (photo_url, source_url))
    except ValueError:
        filenames = ''
    title = unicodedata.normalize('NFKC', (title or '') + ' ' + filenames).replace('_', ' ')
    description = unicodedata.normalize('NFKC', description or '').replace('_', ' ').strip()
    # Long source narratives often discuss unrelated history. The opening image
    # caption can still identify an aerial view before credits/licence boilerplate.
    caption = description if len(description) <= 500 else re.split(r'(?<=[.!?])\s|\n', description, maxsplit=1)[0][:500]
    return any(AIR_VIEW.search(text) or TOWER_VIEW.search(text) for text in (title, caption))
