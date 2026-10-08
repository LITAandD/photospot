"""Reviewed branch photos. Titles and coordinates must agree before attaching."""
import json
from functools import lru_cache
from . import place_catalog as catalog
from .place_categories import GROUPS
from .dining_curation import match as curated_branch

@lru_cache(maxsize=1)
def reviewed():
    return json.loads((catalog.ROOT/'pipeline/data/cafe_photos.json').read_text(encoding='utf-8'))

def matches(places):
    by_id={p['id']:p for p in places}
    result={}
    for entry in reviewed():
        place=by_id.get(entry['place_id'])
        if not place or place['category'] not in GROUPS['cafe'] or catalog.distance_m(entry['lat'],entry['lng'],place)>50: continue
        if entry['place_id'] in result: raise ValueError('Duplicate cafe photo branch')
        result[entry['place_id']]=entry
    return result

def display_name(place):
    curated = curated_branch(place)
    if curated: return curated['display_name']
    entry=matches([place]).get(place['id'])
    return entry['branch'] if entry else place['name']

def files_for(entry):
    return list(dict.fromkeys([entry['file'], *entry.get('extra_files', [])]))

def import_reviewed():
    from .catalog_photos import PublicClient, import_files
    with catalog.connect() as conn:
        places=[dict(r) for r in conn.execute("SELECT * FROM places WHERE active=1 AND category IN ('cafe','bakery','restaurant')")]
    files={}
    for pid,e in matches(places).items():
        for index, title in enumerate(files_for(e)):
            files.setdefault(title,{})[pid]=('reviewed:branch',e['verified_by'],1 if index == 0 else 30 + index)
    return import_files(PublicClient(),files)

if __name__=='__main__': print('Cafe photo links:',len(import_reviewed()))
