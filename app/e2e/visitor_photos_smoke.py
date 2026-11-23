"""Local-only visitor-photo browser workflow. Synthetic pixels; no production calls."""
import os
from pathlib import Path
import sys
import json
import shutil
import argparse
from urllib.parse import urlparse
from PIL import Image, ImageDraw
import sqlite3
from playwright.sync_api import sync_playwright, expect
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8320')
parser.add_argument('--browser', choices=['chromium', 'webkit'], default='chromium')
args = parser.parse_args()
base = args.url.rstrip('/')
assert urlparse(base).hostname in {'127.0.0.1', 'localhost'}, 'Synthetic submissions must remain local'
(ROOT / 'artifacts').mkdir(exist_ok=True)
os.environ['APP_ENV'] = 'test'
os.environ.pop('VERCEL', None)
os.environ.pop('VISITOR_PHOTOS_DATABASE_URL', None)
os.environ.setdefault('VISITOR_PHOTOS_TEST_SQLITE', str(ROOT / 'artifacts/e2e-visitor.sqlite3'))
catalog_copy = ROOT / 'artifacts/e2e-visitor-catalog.sqlite3'
shutil.copyfile(ROOT / 'catalog/places.sqlite3', catalog_copy)
os.environ['PLACE_CATALOG_DB'] = str(catalog_copy)
from api import visitor_photos as store
with sqlite3.connect(catalog_copy) as db:
 pid = db.execute("SELECT id FROM places WHERE name='경복궁' AND active=1").fetchone()[0]
path = f'/browse/{pid}?city=seoul&date=2026-11-23&traffic=test'
fixture = ROOT / 'artifacts/fixture-photo.jpg'
img = Image.new('RGB', (960, 720), 'white')
draw = ImageDraw.Draw(img)
for x in range(0, 960, 4):
 draw.line((x, 0, x, 720), fill='black', width=2)
img.save(fixture, 'JPEG', quality=88)
out = ROOT / 'artifacts/visitor-photo-e2e'
out.mkdir(exist_ok=True)
results = []
with sync_playwright() as pw:
 browser = getattr(pw, args.browser).launch()
 for device,width,height in [('mobile',390,844),('desktop',1280,900),('no-filter',390,844)]:
  c = browser.new_context(viewport={'width':width,'height':height})
  if args.browser == 'chromium': c.grant_permissions(['clipboard-read', 'clipboard-write'])
  if device == 'no-filter': c.add_init_script('delete CanvasRenderingContext2D.prototype.filter')
  page=c.new_page()
  events=[];errors=[]
  page.on('request',lambda r:events.append(r.url) if '/events' in r.url else None)
  page.on('pageerror',lambda e:errors.append(str(e)))
  assert page.request.get(base+'/policies/visitor-photos.html').status == 200
  sitemap=page.request.get(base+'/sitemap.xml')
  assert sitemap.status == 200 and sitemap.text().count('/policies/visitor-photos.html') == 1
  policy=page.request.get(base+'/preview/visitor-photos/policy')
  assert policy.status == 200 and policy.json()['enabled'] is True, policy.text()
  page.goto(base+path)
  try:
   page.get_by_role('button',name='내 사진을 예시로 제안하기',exact=True).click(timeout=60000)
  except Exception:
   page.screenshot(path=str(out/(device+'-failure.png')),full_page=True)
   print({'page_errors':errors,'page_text':page.locator('body').inner_text()},flush=True)
   raise
  page.get_by_test_id('visitor-file').set_input_files(str(ROOT/'artifacts/fixture-photo.jpg'))
  page.get_by_label('사진 속 인물',exact=True).select_option('self')
  canvas=page.get_by_test_id('visitor-preview')
  expect(canvas).to_be_visible()
  slider=page.get_by_role('slider',name='얼굴 1 너비',exact=True)
  slider.focus();slider.press('ArrowRight')
  expect(slider).to_have_value('31')
  page.get_by_role('textbox',name='공개할 이름 · 닉네임 (40자 이내)',exact=True).fill('테스트 촬영자')
  page.get_by_role('textbox',name='촬영 위치·구도 설명 (선택, 160자 이내)',exact=True).fill('테스트 전용 구도')
  send=page.get_by_role('button',name='검수 요청 보내기',exact=True)
  expect(send).to_be_disabled()
  # Seven mandatory rights/privacy/overseas checks; then self-face permission.
  checkboxes=page.get_by_role('checkbox')
  assert checkboxes.count()==10
  checkboxes.first.focus();page.keyboard.press('Space')
  expect(checkboxes.first).to_be_checked()
  for i in range(1,7):checkboxes.nth(i).check()
  expect(send).to_be_disabled()
  checkboxes.nth(7).check()
  expect(send).to_be_enabled()
  if device == 'no-filter':
   ratio=canvas.evaluate('''c => {const ctx=c.getContext('2d'); const variance=(x,y,w,h)=>{const d=ctx.getImageData(x,y,w,h).data;const a=[];for(let i=0;i<d.length;i+=4)a.push(d[i]);const m=a.reduce((a,b)=>a+b,0)/a.length;return a.reduce((s,v)=>s+(v-m)**2,0)/a.length;};return variance(c.width*.4,c.height*.2,40,40)/variance(0,0,40,40);}''')
   assert ratio < .5, ratio
  canvas.screenshot(path=str(out/(device+'-blur-preview.png')))
  page.screenshot(path=str(out/(device+'-form.png')),full_page=True)
  # A failed private preview must not resubmit an accepted photo or throw.
  page.route('**/receipts/*/image', lambda route: route.abort())
  send.click()
  expect(page.get_by_text('검수 대기',exact=True)).to_be_visible(timeout=30000)
  retry=page.get_by_role('button',name='처리본 다시 보기',exact=True)
  expect(retry).to_be_visible()
  page.unroute('**/receipts/*/image')
  retry.click()
  expect(page.get_by_role('img',name='실제로 보관된 얼굴 블러 처리 사진',exact=True)).to_be_visible()
  receipt=page.get_by_role('textbox',name='접수 관리 코드',exact=True).input_value()
  codebox=page.get_by_role('textbox',name='접수 관리 코드',exact=True)
  expect(codebox).to_have_attribute('autocapitalize','none')
  expect(codebox).to_have_attribute('spellcheck','false')
  page.get_by_role('button',name='관리 코드 복사',exact=True).click()
  if args.browser == 'chromium':
   expect(page.get_by_text('관리 코드를 복사했어요.',exact=True)).to_be_visible()
   assert page.evaluate('navigator.clipboard.readText()') == receipt
  sid,token=receipt.split('.')
  assert page.request.get(base+'/preview/visitor-photos/images/'+sid).status==404
  with store.connection() as conn:
   row=conn.execute('SELECT * FROM visitor_photos WHERE id=%s',(sid,)).fetchone()
   assert json.loads(row['consent'])['analysis'] is False
   assert json.loads(row['consent'])['crop'] is False
  store.review(sid,row['image_sha256'],'local-e2e','approve','',dict(place=True,rights=True,faces=True,scene=True))
  fresh=browser.new_context(viewport={'width':width,'height':height})
  other=fresh.new_page();other.goto(base+path)
  example=other.get_by_role('img',name='테스트 전용 구도',exact=True)
  expect(example).to_be_visible(timeout=60000)
  assert example.evaluate('(img)=>img.complete && img.naturalWidth > 0')
  expect(other.get_by_text('테스트 촬영자 제공 · 얼굴 블러 처리 · 포토스팟 예시 표시 허락',exact=True)).to_be_visible()
  other.screenshot(path=str(out/(device+'-approved.png')),full_page=True)
  page.get_by_role('button',name='접수 상태 확인',exact=True).click()
  expect(page.get_by_text('공개 중',exact=True)).to_be_visible()
  page.get_by_role('button',name='사진 공개 요청 철회',exact=True).click()
  page.get_by_role('button',name='철회 취소',exact=True).click()
  assert page.request.get(base+'/preview/visitor-photos/images/'+sid).status==200
  page.get_by_role('button',name='사진 공개 요청 철회',exact=True).click()
  page.get_by_role('button',name='철회하고 사진 삭제',exact=True).click()
  expect(page.get_by_text('철회 완료',exact=True)).to_be_visible()
  assert page.request.get(base+'/preview/visitor-photos/images/'+sid).status==404
  other.reload()
  expect(other.get_by_role('button',name='내 사진을 예시로 제안하기',exact=True)).to_be_visible(timeout=60000)
  expect(other.get_by_role('img',name='테스트 전용 구도',exact=True)).to_have_count(0)
  assert 'city=seoul' in other.url and 'date=2026-11-23' in other.url
  assert not events and not errors,(events,errors)
  results.append({'device':device,'status':'PASS','analytics_requests':len(events),'errors':errors})
  print(json.dumps(results[-1]),flush=True)
  fresh.close();c.close()
 browser.close()
(out/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')

