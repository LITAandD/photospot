"""Read-only Commons metadata research; no automatic branch attachment."""
import json
from pipeline.catalog_photos import PublicClient, COMMONS, plain
from pipeline.place_catalog import ROOT, connect, distance_m

def main():
    client = PublicClient()
    categories = ['Category:Starbucks Coffee in Seoul', 'Category:Cafés in Seoul']
    files = set()
    for category in categories:
        raw = client.get(COMMONS, {'action':'query','format':'json','list':'categorymembers','cmtitle':category,'cmlimit':200})
        members = raw.get('query',{}).get('categorymembers',[])
        print(category, json.dumps(members,ensure_ascii=False),flush=True)
        files.update(r['title'] for r in members if r['ns']==6)
    allpages=[]
    titles=sorted(files)
    for i in range(0,len(titles),20):
        raw = client.get(COMMONS, {'action':'query','format':'json','prop':'imageinfo','titles':'|'.join(titles[i:i+20]),
                                 'iiprop':'url|size|mime|extmetadata','iiurlwidth':960})
        allpages.extend(raw.get('query',{}).get('pages',{}).values())
    dest=ROOT/'artifacts/cafe-photo-research.json'
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(allpages,ensure_ascii=False),encoding='utf-8')
    with connect() as conn:
        cafes=[dict(r) for r in conn.execute("SELECT id,name,lat,lng,address,tags FROM places WHERE category='cafe' AND active=1")]
    for page in allpages:
        meta={k:plain(v.get('value')) for k,v in page.get('imageinfo',[{}])[0].get('extmetadata',{}).items()}
        nearby=[]
        try:
            lat,lng=float(meta['GPSLatitude']),float(meta['GPSLongitude'])
            nearby=sorted(((distance_m(lat,lng,c),c['id'],c['name'],c['address']) for c in cafes))[:3]
        except (KeyError,ValueError): pass
        print(json.dumps({'title':page['title'],'description':meta.get('ImageDescription'),'nearby':nearby},ensure_ascii=False),flush=True)

if __name__=='__main__': main()
