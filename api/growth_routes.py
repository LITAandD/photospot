"""Authenticated product features; all mutations use PostgreSQL transactions."""
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from uuid import UUID
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .auth import CurrentUser, current_user, require_admin
from .db import get_conn
from . import growth_models as M, growth_services as service, catalog_bridge
from pipeline.place_categories import group_for
from pipeline.cafe_photos import display_name
from pipeline.catalog_photos import photos_for

router = APIRouter(prefix='/v1', tags=['growth'])

def audit(conn, actor, action, target):
    conn.execute('INSERT INTO growth_audit(actor_id,action,target_id) VALUES (%s,%s,%s)', (actor, action, target))

def lock_active_user(conn, user_id):
    if not conn.execute('SELECT id FROM users WHERE id=%s AND deleted_at IS NULL FOR UPDATE', (user_id,)).fetchone():
        raise HTTPException(401, '사용할 수 없는 계정이에요')

def billing_status(conn, settings, user_id):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT premium_until, management_url, checked_at FROM billing_entitlements WHERE user_id=%s', (user_id,))
        row = cur.fetchone() or {}
    if settings.revenuecat_secret_key and row and row['checked_at'] < datetime.now(timezone.utc)-timedelta(minutes=15):
        try: until, url = service.subscription(settings, user_id)
        except Exception: raise HTTPException(503, '구독 상태를 확인하지 못했어요. 잠시 후 다시 시도해 주세요')
        conn.execute('UPDATE billing_entitlements SET premium_until=%s,management_url=%s,checked_at=now() WHERE user_id=%s', (until,url,user_id))
        row = {'premium_until':until,'management_url':url}
    until = row.get('premium_until')
    return {'user_id': user_id, 'configured': bool(settings.revenuecat_secret_key), 'premium_until': until,
            'premium': bool(until and until > datetime.now(timezone.utc)), 'management_url': row.get('management_url')}

@router.get('/me/session', response_model=M.GrowthSession)
def session(request: Request, user: CurrentUser = Depends(current_user)):
    s = request.app.state.settings
    return {'user_id': user.id, 'is_admin': user.is_admin, 'instagram_configured': bool(s.instagram_client_id),
            'billing_configured': bool(s.revenuecat_secret_key), 'ai_configured': bool(s.openai_api_key)}

@router.get('/me/instagram')
def instagram(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT username,connected_at FROM social_connections WHERE user_id=%s', (user.id,))
        return cur.fetchone()

@router.post('/me/instagram/authorize')
def authorize_instagram(request: Request, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    s = request.app.state.settings
    if not s.instagram_client_id: raise HTTPException(503, 'Instagram 연결을 준비 중이에요')
    lock_active_user(conn, user.id)
    state = secrets.token_urlsafe(32)
    conn.execute('DELETE FROM social_oauth_states WHERE user_id=%s OR expires_at < now()', (user.id,))
    conn.execute("INSERT INTO social_oauth_states(state_hash,user_id,expires_at) VALUES (%s,%s,now()+interval '10 minutes')", (hashlib.sha256(state.encode()).hexdigest(), user.id))
    return {'url': 'https://www.instagram.com/oauth/authorize?' + urlencode({
        'client_id': s.instagram_client_id, 'redirect_uri': s.instagram_redirect_uri, 'response_type': 'code',
        'scope': 'instagram_business_basic', 'state': state, 'enable_fb_login': '0', 'force_authentication': '1'})}

@router.get('/social/instagram/callback', response_class=HTMLResponse)
def instagram_callback(request: Request, state: str = Query(max_length=256), code: str | None = Query(None, max_length=4096),
                       error: str | None = Query(None, max_length=200), conn=Depends(get_conn)):
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    row = conn.execute('UPDATE social_oauth_states SET consumed_at=now() WHERE state_hash=%s AND expires_at>now() AND consumed_at IS NULL RETURNING user_id',
                       (hashlib.sha256(state.encode()).hexdigest(),)).fetchone()
    conn.commit()  # State remains consumed even when the provider fails; never replay a code.
    if not row: raise HTTPException(400, '연결 요청이 만료됐어요. 앱에서 다시 시작해 주세요')
    if error or not code: return HTMLResponse('<p>Instagram 연결을 취소했어요. 앱으로 돌아가 주세요.</p>')
    try: uid, username = service.instagram_identity(request.app.state.settings, code)
    except Exception: raise HTTPException(502, 'Instagram 확인에 실패했어요. 앱에서 다시 시작해 주세요')
    lock_active_user(conn, row[0])
    if not conn.execute('DELETE FROM social_oauth_states WHERE state_hash=%s AND expires_at>now() RETURNING user_id', (state_hash,)).fetchone():
        raise HTTPException(409, '취소되거나 만료된 연결이에요. 앱에서 다시 시작해 주세요')
    conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('instagram:'+uid,))
    owner = conn.execute('SELECT user_id FROM social_connections WHERE instagram_id=%s', (uid,)).fetchone()
    if owner and owner[0] != row[0]: raise HTTPException(409, '이미 다른 계정에 연결된 Instagram이에요')
    conn.execute('INSERT INTO social_connections(user_id,instagram_id,username) VALUES (%s,%s,%s) '
                 'ON CONFLICT(user_id) DO UPDATE SET instagram_id=EXCLUDED.instagram_id, username=EXCLUDED.username, connected_at=now()', (row[0],uid,username))
    return HTMLResponse('<meta name="viewport" content="width=device-width,initial-scale=1"><p>Instagram 계정을 확인했어요. 앱으로 돌아가 연결 상태를 새로고침해 주세요.</p><a href="photospot://accounts">포토스팟으로 돌아가기</a>',
                        headers={'Content-Security-Policy': "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"})

@router.delete('/me/instagram', status_code=204)
def disconnect_instagram(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    lock_active_user(conn, user.id)
    conn.execute('DELETE FROM social_oauth_states WHERE user_id=%s', (user.id,))
    conn.execute('DELETE FROM social_connections WHERE user_id=%s', (user.id,))

@router.get('/me/billing', response_model=M.BillingStatus)
def get_billing(request: Request, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    return billing_status(conn, request.app.state.settings, user.id)

@router.post('/me/billing/sync', response_model=M.BillingStatus)
def sync_billing(request: Request, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    s = request.app.state.settings
    if not s.revenuecat_secret_key: raise HTTPException(503, '스토어 결제를 준비 중이에요')
    lock_active_user(conn, user.id)
    previous = conn.execute("SELECT 1 FROM billing_entitlements WHERE user_id=%s AND checked_at > now()-interval '5 seconds'", (user.id,)).fetchone()
    if previous: return billing_status(conn, s, user.id)
    try: until, url = service.subscription(s, user.id)
    except Exception: raise HTTPException(502, '구매 내역 확인이 지연되고 있어요. 잠시 후 다시 확인해 주세요')
    conn.execute('INSERT INTO billing_entitlements(user_id,premium_until,management_url) VALUES (%s,%s,%s) '
                 'ON CONFLICT(user_id) DO UPDATE SET premium_until=EXCLUDED.premium_until, management_url=EXCLUDED.management_url, checked_at=now()', (user.id,until,url))
    return billing_status(conn, s, user.id)

@router.post('/feedback', response_model=M.FeedbackOut, status_code=201)
def submit_feedback(body: M.FeedbackSubmission, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    lock_active_user(conn, user.id)
    if conn.execute("SELECT count(*) FROM app_feedback WHERE user_id=%s AND created_at>now()-interval '1 day'", (user.id,)).fetchone()[0] >= 5:
        raise HTTPException(429, '의견은 하루 5건까지 보낼 수 있어요')
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('INSERT INTO app_feedback(user_id,category,message,ai_consent) VALUES (%s,%s,%s,%s) RETURNING *',
                    (user.id,body.category,body.message,body.ai_consent))
        return cur.fetchone()

@router.get('/me/feedback', response_model=list[M.FeedbackOut])
def my_feedback(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM app_feedback WHERE user_id=%s ORDER BY created_at DESC LIMIT 100', (user.id,))
        return cur.fetchall()

@router.delete('/me/feedback/{feedback_id}', status_code=204)
def delete_feedback(feedback_id: UUID, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    row = conn.execute('DELETE FROM app_feedback WHERE id=%s AND user_id=%s RETURNING id', (feedback_id,user.id)).fetchone()
    if not row: raise HTTPException(404, '의견을 찾을 수 없어요')
    conn.execute('DELETE FROM feedback_triages WHERE %s=ANY(feedback_ids)', (feedback_id,))

@router.get('/admin/feedback', response_model=list[M.FeedbackOut])
def feedback_queue(_: CurrentUser = Depends(require_admin), conn=Depends(get_conn)):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM app_feedback ORDER BY created_at DESC LIMIT 100')
        return cur.fetchall()

@router.patch('/admin/feedback/{feedback_id}', status_code=204)
def review_feedback(feedback_id: UUID, body: M.FeedbackReview, admin: CurrentUser = Depends(require_admin), conn=Depends(get_conn)):
    row = conn.execute('UPDATE app_feedback SET reviewed_text=%s,reviewed_by=%s,reviewed_at=now() WHERE id=%s AND ai_consent RETURNING id',
                       (service.redact(body.reviewed_text),admin.id,feedback_id)).fetchone()
    if not row: raise HTTPException(409, 'AI 분석에 동의한 의견만 검토할 수 있어요')
    audit(conn,admin.id,'feedback_review',feedback_id)

@router.post('/admin/feedback/triage')
def analyze_feedback(body: M.TriageBatch, request: Request, admin: CurrentUser = Depends(require_admin), conn=Depends(get_conn)):
    s = request.app.state.settings
    if not s.openai_api_key: raise HTTPException(503, '서버의 OpenAI API 키를 설정해 주세요')
    # Serialize analyses and limit spend globally, including concurrent administrators.
    conn.execute('SELECT pg_advisory_xact_lock(73192018)')
    if conn.execute("SELECT count(*) FROM growth_audit WHERE action='ai_triage_attempt' AND created_at>now()-interval '1 day'").fetchone()[0] >= 20:
        raise HTTPException(429, '하루 AI 분석 한도 20회에 도달했어요')
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM app_feedback WHERE id=ANY(%s) AND ai_consent AND reviewed_text IS NOT NULL FOR UPDATE', (body.feedback_ids,))
        rows = cur.fetchall()
    if len(rows) != len(set(body.feedback_ids)): raise HTTPException(409, '동의 및 개인정보 검토가 완료된 의견만 선택해 주세요')
    if conn.execute('SELECT 1 FROM feedback_triages WHERE feedback_ids && %s LIMIT 1', (body.feedback_ids,)).fetchone():
        raise HTTPException(409, '이미 분석한 의견이 포함되어 있어요. 기존 개선안을 확인해 주세요')
    audit(conn,admin.id,'ai_triage_attempt',body.feedback_ids[0])
    try: ideas = service.triage(s, rows)
    except Exception:
        conn.commit()  # Failed requests also count towards the budget.
        raise HTTPException(502, 'AI 분석에 실패했어요. 원본 의견은 보존되어 있어요. 잠시 후 다시 시도해 주세요')
    for idea in ideas:
        conn.execute('INSERT INTO feedback_triages(feedback_ids,result,model) VALUES (%s,%s,%s)',
                     ([UUID(x) for x in idea['feedback_ids']],Jsonb(idea),s.feedback_model))
    return {'created': len(ideas)}

@router.get('/admin/triages')
def list_triages(_: CurrentUser = Depends(require_admin), conn=Depends(get_conn)):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM feedback_triages ORDER BY (result->>'priority_score')::float DESC,created_at DESC LIMIT 100")
        return cur.fetchall()

@router.patch('/admin/triages/{triage_id}', status_code=204)
def decide_triage(triage_id: UUID, body: M.TriageDecision, admin: CurrentUser = Depends(require_admin), conn=Depends(get_conn)):
    row = conn.execute('SELECT status FROM feedback_triages WHERE id=%s FOR UPDATE', (triage_id,)).fetchone()
    if not row: raise HTTPException(404, '개선안을 찾을 수 없어요')
    allowed = {'proposed': {'approved','dismissed'}, 'approved': {'planned','dismissed'}, 'planned': {'done','dismissed'}, 'done': set(), 'dismissed': set()}
    if body.status not in allowed[row[0]]: raise HTTPException(409, '제안 → 승인 → 계획 → 완료 순서로 처리해 주세요')
    conn.execute('UPDATE feedback_triages SET status=%s,review_note=%s,reviewed_by=%s,updated_at=now() WHERE id=%s', (body.status,body.note,admin.id,triage_id))
    audit(conn,admin.id,'triage_'+body.status,triage_id)

@router.post('/admin/campaigns', status_code=201)
def create_campaign(body: M.CampaignIn, admin: CurrentUser = Depends(require_admin), conn=Depends(get_conn)):
    place = catalog_bridge.find(body.place_id)
    if not photos_for([str(body.place_id)]).get(str(body.place_id)): raise HTTPException(409, '실제 장소 사진이 있는 곳만 광고할 수 있어요')
    row = conn.execute('INSERT INTO sponsored_campaigns(place_id,sponsor,headline,placement,starts_at,ends_at,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                       (body.place_id,body.sponsor,body.headline,body.placement,body.starts_at,body.ends_at,admin.id)).fetchone()
    audit(conn,admin.id,'campaign_create',row[0])
    return {'id': str(row[0])}

@router.get('/admin/campaigns')
def campaigns(_: CurrentUser = Depends(require_admin), conn=Depends(get_conn)):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT c.*, (SELECT count(*) FROM campaign_events e WHERE e.campaign_id=c.id AND kind='impression') AS impressions, "
                    "(SELECT count(*) FROM campaign_events e WHERE e.campaign_id=c.id AND kind='click') AS clicks FROM sponsored_campaigns c ORDER BY created_at DESC LIMIT 100")
        return cur.fetchall()

@router.patch('/admin/campaigns/{campaign_id}', status_code=204)
def approve_campaign(campaign_id: UUID, body: M.CampaignApproval, admin: CurrentUser = Depends(require_admin), conn=Depends(get_conn)):
    if not conn.execute('UPDATE sponsored_campaigns SET approved=%s WHERE id=%s RETURNING id', (body.approved,campaign_id)).fetchone(): raise HTTPException(404, '광고를 찾을 수 없어요')
    audit(conn,admin.id,'campaign_approve' if body.approved else 'campaign_pause',campaign_id)

@router.get('/sponsorships')
def sponsorships(request: Request, lat: float = Query(ge=33,le=39), lng: float = Query(ge=124,le=132), radius_m: int = Query(5000,ge=500,le=50000),
                 place_group: str = Query('all',pattern='^(all|cafe|travel|festival)$'), user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    if billing_status(conn,request.app.state.settings,user.id)['premium']: return []
    from pipeline.place_catalog import distance_m
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM sponsored_campaigns WHERE approved AND starts_at<=now() AND ends_at>now() ORDER BY id')
        rows = cur.fetchall()
    eligible = []
    for row in rows:
        try: place = catalog_bridge.find(row['place_id'])
        except HTTPException: continue
        if place_group != 'all' and group_for(place['category']) != place_group: continue
        if distance_m(lat,lng,place) > radius_m: continue
        photo = next(iter(photos_for([str(row['place_id'])]).get(str(row['place_id']), [])), None)
        if photo: eligible.append({**{key:row[key] for key in ('id','place_id','sponsor','headline','placement','starts_at','ends_at','approved')},'place_name':display_name(place),'photo':photo})
    # Rotate each day without auctioning away match scores or profiling the user.
    day = datetime.now(timezone.utc).date().isoformat()
    eligible.sort(key=lambda r: hashlib.sha256((str(r['id'])+day).encode()).hexdigest())
    return [next(r for r in eligible if r['placement']==kind) for kind in ['priority','banner'] if any(r['placement']==kind for r in eligible)]

@router.post('/sponsorships/{campaign_id}/events', status_code=204)
def record_event(campaign_id: UUID, body: M.CampaignEvent, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    if not conn.execute('SELECT 1 FROM sponsored_campaigns WHERE id=%s AND approved AND starts_at<=now() AND ends_at>now()', (campaign_id,)).fetchone(): raise HTTPException(404, '종료된 광고예요')
    conn.execute('INSERT INTO campaign_events(campaign_id,user_id,kind) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (campaign_id,user.id,body.kind))
