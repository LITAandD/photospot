"""Read-only checks on the production domain; no consent changes or analytics writes."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
BASE='https://photospot.litaandd.com'
DATE='2026-11-22'
out=Path('artifacts/release-1118');out.mkdir(parents=True,exist_ok=True)
results=[]
with sync_playwright() as pw:
    for engine,device,city in [('webkit','iPhone 13','gangneung'),('chromium','Pixel 7','jeju'),('chromium',None,'gangneung')]:
        browser=getattr(pw,engine).launch()
        opts=pw.devices[device] if device else {'viewport':{'width':1280,'height':900}}
        ctx=browser.new_context(**opts)
        events=[]
        ctx.route('**/preview/events',lambda r:(events.append(r.request.url),r.abort()))
        page=ctx.new_page()
        response=page.request.get(BASE+'/health');assert response.status==200
        data=page.request.get(f'{BASE}/preview/browse?city={city}&visit_date={DATE}')
        assert data.status==200
        data=data.json();assert len(data['items'])==12
        first=data['items'][0]
        url=f"{BASE}/browse/{first['place_id']}?city={city}&date={DATE}&utm_source=share&traffic=test"
        res=page.goto(url)
        assert res.status==200
        expect(page.get_by_role('heading',level=1,name=first['place_name'])).to_be_visible(timeout=60000)
        expect(page.get_by_text(DATE,exact=False)).to_be_visible()
        expect(page.get_by_role('button',name='이 조건으로 맞춤 추천 설정',exact=True)).to_be_visible()
        page.screenshot(path=str(out/f'production-{engine}-{device or "desktop"}.png'))
        assert not events
        results.append(dict(engine=engine,device=device or 'desktop',physical=False,city=city,
                            status=res.status,public_detail=url,cards=12,
                            first12_blank=sum(not r['cover_photo'] for r in data['items']),analytics=0))
        ctx.close();browser.close()
print(json.dumps(results,ensure_ascii=False))
(out/'production.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
