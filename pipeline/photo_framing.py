"""Thumbnail preferences from image reviews, then conservative metadata hints.

Only descriptions of the pictured space count as close-view evidence. Food,
portraits, signs and isolated exhibits must not become covers merely because
they are close-ups. Unknown framing preserves the catalog's source priority.
"""
import re
import unicodedata
import json
from pathlib import Path


REVIEWS = {(r['photo_url'], r['source_url']): r for r in json.loads(
    (Path(__file__).parent / 'data/photo_framing_reviews.json').read_text(encoding='utf-8'))}
REVIEW_RANKS = {'close_space': 0, 'unknown': 1, 'distant': 2, 'unsuitable': 3}


DISTANT = re.compile(
    r'\b(?:aerial|panoram\w*|skyline|distant|bird[\s\W]*s[\s-]*eye|'
    r'overview|overlook|from afar|from above|in the distance)\b'
    r'|원경|항공|조감|파노라마|멀리서|전경', re.I)
SUBJECT_ONLY = re.compile(
    r'\b(?:portrait|selfie|food|dish|dessert|pastry|cake|coffee cup|menu|'
    r'logo|sign|signage|marker|statue|sculpture|tiles?|artifact|exhibit|'
    r'ceremony|honou?r guard|soldiers?|minister|secretary|demonstration)\b'
    r'|인물|셀카|음식|디저트|메뉴|간판|표지판|안내판|조각상|동상|유물|행사|기념식', re.I)
CLOSE_SPACE = re.compile(
    r'\b(?:interiors?|entrances?|courtyards?|doorways?|foyers?|lobb(?:y|ies)|inside view)\b'
    r'|실내|내부|입구|근경|근접|中庭|室内|入口', re.I)
CLOSE_UP = re.compile(r'\bclose[\s-]*up\b', re.I)
SPACE = re.compile(r'\b(?:space|room|building|facade|façade|alley|path|terrace|garden)\b'
                   r'|공간|건물|골목|산책로|테라스|정원', re.I)


def thumbnail_rank(title='', description='', match_method='', photo_url='', source_url='') -> int:
    """0: likely close space, 1: unknown, 2: distant, 3: subject-only.

    The short description supplied with a photo can identify its framing;
    long encyclopedia/event narratives cannot. Reject conflicting far-view
    or subject-only cues before considering an entrance/interior mention.
    P5775 explicitly identifies an interior photograph in Wikidata.
    """
    # Match both the actual image and its source. A changed photo must not
    # inherit an old visual judgement simply because it has the same title.
    review = REVIEWS.get((photo_url, source_url))
    if review:
        return REVIEW_RANKS[review['framing']]
    title = unicodedata.normalize('NFKC', title or '').replace('_', ' ')
    description = unicodedata.normalize('NFKC', description or '').strip()
    text = title + ' ' + (description if len(description) <= 500 else '')
    if SUBJECT_ONLY.search(text):
        return 3
    if DISTANT.search(text):
        return 2
    if (CLOSE_SPACE.search(text) or (CLOSE_UP.search(text) and SPACE.search(text))
            or match_method == 'wikidata:P5775'):
        return 0
    return 1


def prefer_close_views(ranked_photos):
    """Close space, unknown, distant, subject-only; stable source order within each rank."""
    ranked_photos = sorted(ranked_photos, key=lambda item: item[0])
    return [photo for _, photo in ranked_photos]
