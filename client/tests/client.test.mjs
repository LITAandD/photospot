import test from 'node:test';
import assert from 'node:assert/strict';
import { PhotoSpotClient, ApiError, finishOnboarding } from '../dist/index.js';

const json = (body, status = 200) => new Response(JSON.stringify(body), { status });
test('linking another identity preserves the signed-in account tokens', async()=>{
  const s=setup(async(url,init)=>{assert.ok(url.endsWith('/me/identities/apple'));assert.equal(JSON.parse(init.body).authorization_code,'code');return new Response(null,{status:204});});
  await s.client.linkIdentity('apple','provider-token',{nonce:'nonce',authorizationCode:'code'});
  assert.deepEqual(s.value(),{access:'expired',refresh:'refresh-1'});
});
test('billing sync never trusts client supplied payment state or user id',async()=>{
  const s=setup(async(url,init)=>{assert.ok(url.endsWith('/me/billing/sync'));assert.equal(init.body,undefined);assert.equal(init.headers.Authorization,'Bearer expired');return json({premium:false});});
  assert.equal((await s.client.syncBilling()).premium,false);
});
test('Apple code and deletion proof reach the server without being saved as session tokens', async () => {
  const calls=[];
  const s=setup(async (url,init)=>{ calls.push({url,body:JSON.parse(init.body)}); return url.endsWith('/apple') ? json({access_token:'app-access',refresh_token:'app-refresh'}) : new Response(null,{status:204}); });
  await s.client.auth.apple('id-token',{nonce:'nonce',authorizationCode:'one-time-code'});
  assert.equal(calls[0].body.authorization_code,'one-time-code');
  assert.deepEqual(s.value(),{access:'app-access',refresh:'app-refresh'});
  const proof={apple:{identity_token:'reauth-token',authorization_code:'new-code',nonce:'nonce'}};
  await s.client.deleteAccount(proof);
  assert.deepEqual(calls[1].body,proof);
  assert.equal(s.value(),null);
});
function setup(fetch) {
  let value = { access: 'expired', refresh: 'refresh-1' };
  let signedOut = 0;
  const tokens = { get: () => value, set: (next) => { value = next; }, clear: () => { value = null; } };
  const client = new PhotoSpotClient({ baseUrl: 'https://test.invalid', tokens, fetch,
    onSignedOut: () => signedOut++ });
  return { client, tokens, value: () => value, signedOut: () => signedOut };
}

test('concurrent 401s rotate refresh token once and retry with the new access token', async () => {
  let refreshes = 0;
  const s = setup(async (url, init) => {
    if (url.endsWith('/refresh')) { refreshes++; await new Promise((r) => setTimeout(r, 15)); return json({ access_token: 'new', refresh_token: 'refresh-2' }); }
    return init.headers.Authorization === 'Bearer new' ? json({ gender: 'undisclosed' }) : json({ title: 'Expired' }, 401);
  });
  await Promise.all([s.client.getProfile(), s.client.getTypeCard()]);
  assert.equal(refreshes, 1);
  assert.equal(s.value().refresh, 'refresh-2');
});

test('a late 401 reuses a token already refreshed by another request', async () => {
  let refreshes = 0;
  const s = setup(async (url, init) => {
    if (url.endsWith('/refresh')) { refreshes++; return json({ access_token: 'new', refresh_token: 'refresh-2' }); }
    if (init.headers.Authorization === 'Bearer new') return json({});
    if (url.endsWith('/type-card')) await new Promise((r) => setTimeout(r, 30));
    return json({}, 401);
  });
  await Promise.all([s.client.getProfile(), s.client.getTypeCard()]);
  assert.equal(refreshes, 1);
});

test('network or server failure during refresh preserves the saved session', async () => {
  for (const failure of ['offline', 'server']) {
    const s = setup(async (url) => {
      if (url.endsWith('/refresh')) { if (failure === 'offline') throw new TypeError('offline'); return json({ title: 'Try later' }, 503); }
      return json({}, 401);
    });
    await assert.rejects(s.client.getProfile());
    assert.equal(s.value().refresh, 'refresh-1');
    assert.equal(s.signedOut(), 0);
  }
});

test('invalid refresh clears tokens and notifies the app', async () => {
  const s = setup(async () => json({ title: 'Login again' }, 401));
  await assert.rejects(s.client.getProfile(), ApiError);
  assert.equal(s.value(), null);
  assert.equal(s.signedOut(), 1);
});

test('in-flight refresh cannot restore a logged-out session', async () => {
  let release, started;
  const waiting = new Promise((r) => { started = r; });
  const s = setup(async (url) => {
    if (url.endsWith('/refresh')) { started(); await new Promise((r) => { release = r; }); return json({ access_token: 'new', refresh_token: 'new-refresh' }); }
    if (url.endsWith('/logout')) return new Response(null, { status: 204 });
    return json({}, 401);
  });
  const request = s.client.getProfile();
  await waiting;
  await s.client.auth.logout();
  release();
  await assert.rejects(request, ApiError);
  assert.equal(s.value(), null);
});

test('missing tokens do not permanently wedge future refresh attempts', async () => {
  const s = setup(async (url, init) => url.endsWith('/refresh') ? json({ access_token: 'new', refresh_token: 'next' })
    : init.headers.Authorization === 'Bearer new' ? json({}) : json({}, 401));
  s.tokens.clear();
  await assert.rejects(s.client.getProfile());
  s.tokens.set({ access: 'expired', refresh: 'refresh-1' });
  await s.client.getProfile();
  assert.equal(s.value().access, 'new');
});

test('HTML gateway errors keep their HTTP status', async () => {
  const s = setup(async () => new Response('<html>Unavailable</html>', { status: 503 }));
  await assert.rejects(s.client.getProfile(), (e) => e instanceof ApiError && e.status === 503 && e.title.length > 0);
});

test('web photo upload sends a real file and the selected spot ID', async () => {
  const s = setup(async (_url, init) => {
    assert.ok(init.body instanceof FormData);
    assert.equal(init.body.get('spot_id'), 'spot-123');
    assert.equal(await init.body.get('file').text(), 'image-content');
    assert.equal(init.headers['Content-Type'], undefined);
    return json({ photo_id: 'photo-1', job_queued: true, taken_at: null }, 202);
  });
  await s.client.uploadPhoto('spot-123', new Blob(['image-content'], { type: 'image/jpeg' }));
});

test('successful deletion clears local tokens; failed deletion keeps them', async () => {
  const success = setup(async () => new Response(null, { status: 204 }));
  await success.client.deleteAccount();
  assert.equal(success.value(), null);
  const failure = setup(async () => json({ title: 'Try later' }, 503));
  await assert.rejects(failure.client.deleteAccount());
  assert.ok(failure.value());
});

test('onboarding saves only the profile and leaves saved saju unchanged', async () => {
  const requests = [];
  const s = setup(async (url, init) => { requests.push([new URL(url).pathname, init.method]); return json({}); });
  await finishOnboarding(s.client, { profile: { gender: 'undisclosed' } });
  assert.deepEqual(requests, [['/v1/me/consents', 'POST'], ['/v1/me/profile', 'PUT'], ['/v1/me/type-card', 'GET']]);
});

test('the optional saju selection is explicit and consistent in list and detail', async () => {
  const urls = [];
  const s = setup(async (url) => { urls.push(new URL(url)); return json({}); });
  await s.client.getRecommendations({ lat: 37.5, lng: 127, date: '2026-10-10' });
  await s.client.getRecommendations({ lat: 37.5, lng: 127, date: '2026-10-13', useSaju: true });
  await s.client.getPlace('place-1', '2026-10-13', true);
  assert.equal(urls[0].searchParams.get('use_saju'), 'false');
  for (const url of urls.slice(1)) {
    assert.equal(url.searchParams.get('use_saju'), 'true');
    assert.equal(url.searchParams.get('date'), '2026-10-13');
  }
});

test('place groups are sent to the API with all as the default', async () => {
  const urls = [];
  const s = setup(async (url) => { urls.push(new URL(url)); return json({}); });
  for (const placeGroup of [undefined, 'cafe', 'travel', 'festival']) {
    await s.client.getRecommendations({ lat: 37.5, lng: 127, date: '2026-10-10', placeGroup });
  }
  assert.deepEqual(urls.map((url) => url.searchParams.get('place_group')), ['all', 'cafe', 'travel', 'festival']);
});
