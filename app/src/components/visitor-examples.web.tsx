import React, { useEffect, useRef, useState } from 'react';
import { Pressable, View } from 'react-native';
import { Body, Button, Card, ErrorBox, Field, Muted } from './ui';
import { colors, fonts } from '@/theme';
import { freshReceipt, parseReceipt, receiptState, visitorBase, visitorRequest, VisitorPhotoError, type ExamplePhoto, type FaceBox, type Receipt, type VisitorPolicy } from '@/visitor-photos';

const labels = {
  rights: '직접 촬영했거나 촬영자에게 제출·공개 허락을 받았어요.',
  location: '이 장소에서 찍은 실제 사진이고, 다른 지점 사진이나 AI 생성 이미지가 아니에요.',
  age14: '만 14세 이상이에요.',
  publication: '검수 후 포토스팟 웹의 사용자 촬영 예시로 공개하는 데 동의해요.',
  processing: '얼굴 가림·위치정보 등 메타데이터 삭제·비율을 유지한 크기 조정·재저장에 동의해요.',
  privacy: '사진과 표시 이름의 수집·이용, 보관 기간과 삭제 방법을 읽고 동의해요.',
  overseas: '안내된 사진·접수 정보의 Neon 싱가포르 저장 및 국외 처리에 동의해요. 동의하지 않아도 장소 둘러보기는 이용할 수 있어요.',
  face_blur: '사진 속 인물은 본인이며, 얼굴 전체를 블러 처리한 뒤 공개하는 데 동의해요. 다른 사람은 식별되지 않아요.',
  crop: '(선택) 추후 썸네일 크롭을 허용해요.',
  analysis: '(선택) 추후 사진 색상·배경 형태 분석을 허용해요. AI 학습 동의는 포함하지 않아요.',
};
type Choice = Record<keyof typeof labels, boolean>;
const initial: Choice = { rights: false, location: false, age14: false, publication: false, processing: false, privacy: false, overseas: false, face_blur: false, crop: false, analysis: false };
function Check({ name, checked, onChange, disabled }: { name: keyof Choice; checked: boolean; onChange: () => void; disabled: boolean }) {
  return <Pressable accessibilityRole="checkbox" aria-checked={checked} accessibilityLabel={labels[name]}
    disabled={disabled} accessibilityState={{ checked, disabled }} onPress={onChange} style={{ paddingVertical: 10, minHeight: 44, flexDirection: 'row', gap: 8 }}>
    <Body>{checked ? '☑' : '□'}</Body><View style={{ flex: 1 }}><Body size={13}>{labels[name]}</Body></View>
  </Pressable>;
}
const defaultBox = (): FaceBox => ({ x: .35, y: .15, width: .3, height: .3 });

export function VisitorExamples(props: { placeId: string; placeName: string }) {
  // Route reuse must discard the previous place's file, receipt, and permissions.
  return <Examples key={props.placeId} {...props} />;
}
function Examples({ placeId, placeName }: { placeId: string; placeName: string }) {
  const [policy, setPolicy] = useState<VisitorPolicy | null>(null);
  const [items, setItems] = useState<ExamplePhoto[]>([]);
  const [open, setOpen] = useState(false), [manage, setManage] = useState(false);
  const [error, setError] = useState<string | null>(null), [busy, setBusy] = useState(false);
  const sending = useRef(false), mounted = useRef(true);
  const [file, setFile] = useState<File | null>(null), [url, setUrl] = useState('');
  const [subject, setSubject] = useState<'space' | 'self'>('space'), [faces, setFaces] = useState<FaceBox[]>([]);
  const [choice, setChoice] = useState<Choice>(initial), [credit, setCredit] = useState(''), [caption, setCaption] = useState('');
  const canvas = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null), [code, setCode] = useState('');
  const [confirmWithdraw, setConfirmWithdraw] = useState(false), [sentPreview, setSentPreview] = useState('');
  const [previewError, setPreviewError] = useState(false), [previewBusy, setPreviewBusy] = useState(false);
  const requestKey = useRef<ReturnType<typeof freshReceipt> | null>(null);
  const payload = useRef<unknown>(null); // Retry the same bytes/permissions after a lost response.
  const [attempted, setAttempted] = useState(false);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    void visitorRequest<VisitorPolicy>('/policy', undefined, undefined, controller.signal).then(p => {
      if (controller.signal.aborted) return;
      setPolicy(p);
      if (p.enabled) return visitorRequest<{ items: ExamplePhoto[] }>('/places/' + encodeURIComponent(placeId), undefined, undefined, controller.signal)
        .then(data => { if (!controller.signal.aborted) setItems(data.items); });
    }).catch(() => { /* optional feature never prevents place information */ });
    return () => { mounted.current = false; controller.abort(); };
  }, [placeId]);
  useEffect(() => { if (!file) { setUrl(''); return; } const u = URL.createObjectURL(file); setUrl(u); return () => URL.revokeObjectURL(u); }, [file]);
  useEffect(() => () => { if (sentPreview) URL.revokeObjectURL(sentPreview); }, [sentPreview]);
  useEffect(() => {
    setReady(false);
    if (!url) return;
    let cancelled = false;
    const image = new Image();
    image.onload = () => {
      if (cancelled || !canvas.current) return;
      const c = canvas.current, scale = Math.min(1, 640 / image.naturalWidth);
      c.width = Math.round(image.naturalWidth * scale); c.height = Math.round(image.naturalHeight * scale);
      const ctx = c.getContext('2d'); if (!ctx) return;
      ctx.drawImage(image, 0, 0, c.width, c.height);
      for (const box of faces) {
        // Browser approximation; the server re-decodes and applies the stored mask.
        const x = box.x * c.width, y = box.y * c.height, w = box.width * c.width, h = box.height * c.height;
        ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
        ctx.filter = 'blur(' + Math.max(w, h) * .28 + 'px)';
        ctx.drawImage(image, 0, 0, c.width, c.height); ctx.restore();
        ctx.strokeStyle = '#9d3d20'; ctx.lineWidth = 2; ctx.strokeRect(x, y, w, h);
      }
      setReady(true);
    };
    image.onerror = () => { if (!cancelled) setError('이 브라우저에서 사진을 열지 못했어요. JPEG·PNG·WebP를 선택해 주세요.'); };
    image.src = url;
    return () => { cancelled = true; image.onload = null; image.onerror = null; };
  }, [url, faces, open, attempted]);
  const required = ['rights', 'location', 'age14', 'publication', 'processing', 'privacy', 'overseas'] as const;
  const canSubmit = !!file && ready && !!credit.trim() && required.every(k => choice[k]) && (subject === 'space' || choice.face_blur && faces.length > 0);
  const showStored = async (key: { id: string; token: string }) => {
    setPreviewBusy(true); setPreviewError(false);
    try {
      const response = await fetch(visitorBase() + '/receipts/' + key.id + '/image', { method: 'POST', credentials: 'omit',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key.token }, body: '{}' });
      if (!response.ok) throw new Error('preview unavailable');
      const blob = await response.blob();
      if (mounted.current) setSentPreview(URL.createObjectURL(blob));
    } catch { if (mounted.current) setPreviewError(true); }
    finally { if (mounted.current) setPreviewBusy(false); }
  };
  const submit = async () => {
    if (sending.current || (!canSubmit && !attempted)) return;
    sending.current = true; setBusy(true); setError(null); setAttempted(true);
    try {
      if (!requestKey.current) {
        requestKey.current = freshReceipt();
        setCode(requestKey.current.id + '.' + requestKey.current.token);
      }
      if (!payload.current) {
        const bytes = new Uint8Array(await file!.arrayBuffer());
        // Files are capped at 2 MiB; chunking avoids a huge apply/spread stack.
        let binary = ''; for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        payload.current = { ...requestKey.current, place_id: placeId, credit, caption, image: btoa(binary), faces,
          consent: { ...choice, subject, version: policy!.version } };
      }
      const result = await visitorRequest<Receipt>('', payload.current);
      if (!mounted.current) return;
      setReceipt(result); setFile(null); payload.current = null;
      void showStored(requestKey.current);
    } catch (e) { if (mounted.current) {
      setError(e instanceof Error ? e.message : '접수하지 못했어요. 관리 코드를 보관하고 다시 시도해 주세요.');
      if (e instanceof VisitorPhotoError && [400, 403, 404, 413, 422].includes(e.status)) {
        setAttempted(false); payload.current = null; requestKey.current = null; setCode('');
      }
    } }
    finally { sending.current = false; if (mounted.current) setBusy(false); }
  };
  const checkStatus = async (withdraw = false) => {
    if (sending.current) return;
    const key = parseReceipt(code);
    if (!key) { setError('접수 관리 코드를 확인해 주세요.'); return; }
    sending.current = true; setBusy(true); setError(null);
    try {
      if (withdraw) {
        await visitorRequest('/receipts/' + key.id + '/withdraw', {}, key.token);
        setReceipt({ id: key.id, state: 'withdrawn' }); setSentPreview(''); setPreviewError(false); setConfirmWithdraw(false);
        setItems(old => old.filter(item => item.id !== key.id));
      } else { setReceipt(await visitorRequest<Receipt>('/receipts/' + key.id, undefined, key.token)); }
    } catch (e) { setError(e instanceof Error ? e.message : '접수 상태를 확인하지 못했어요.'); }
    finally { sending.current = false; setBusy(false); }
  };
  // Keep management accessible through the page even when intake is paused.
  if (!policy) return null;
  const inputStyle = { color: colors.ink, fontFamily: fonts.body, width: '100%', minHeight: 44 };
  return <Card style={{ gap: 14 }}>
    <Body headingLevel={2}>사용자 촬영 예시</Body>
    <Muted size={12}>대표사진·정합도 평가와 별개예요. 얼굴을 가린 검수 완료 사진만 공개해요.</Muted>
    {items.map(photo => <View key={photo.id} style={{ gap: 6 }}>
      <img src={(process.env.EXPO_PUBLIC_PREVIEW_API_URL ?? '').replace(/\/$/, '') + photo.url}
        alt={photo.caption || placeName + ' 사용자 촬영 예시'} loading="lazy" style={{ width: '100%', maxHeight: 420, objectFit: 'contain' }} />
      <Muted size={12}>{photo.credit} 제공{photo.face_blurred ? ' · 얼굴 블러 처리' : ''} · 포토스팟 예시 표시 허락</Muted>
      {photo.caption ? <Body size={13}>{photo.caption}</Body> : null}
    </View>)}
    {policy.enabled ? <Button title={open ? '사진 등록 접기' : '내 사진을 예시로 제안하기'} variant="outline"
      disabled={busy} onPress={() => setOpen(!open)} /> : <Muted size={12}>사진 접수를 준비하고 있어요.</Muted>}
    {open && policy.enabled ? <View style={{ gap: 14 }}>
      <Body headingLevel={2}>{placeName}에 사진 제안</Body>
      <Muted>등록 즉시 공개되지 않아요. 공간과 촬영 구도가 보이는 사진을 골라 주세요. 타인의 식별 가능한 얼굴, 아동이 중심인 사진, 작품·메뉴만 찍은 사진은 받지 않아요.</Muted>
      <Muted>본인 얼굴은 머리 전체와 거울·유리에 비친 얼굴까지 영역을 지정해 주세요. 자동 얼굴 검출 기능은 아니며, 블러만으로 완전한 익명성이 보장되지는 않아요.</Muted>
      <Body size={12}>{policy.operator} · 문의: {policy.contact}. 검수 대기 최대 {policy.pending_days}일, 승인 후 공개 최대 {policy.public_days}일. 철회하면 사진을 삭제하고 접수 기록은 최대 {policy.pending_days}일 보관해요. 접수 관리 코드는 이 화면을 떠나기 전에 따로 보관해 주세요.</Body>
      <a href={policy.policy_url} target="_blank" rel="noopener noreferrer" style={{ color: colors.accentInk }}>사진 제출·개인정보 안내</a>
      <Muted size={12}>처리본·닉네임·설명·장소·동의·접수 정보는 제출 시 암호화 전송되어 Neon(privacy@neon.tech)의 싱가포르 DB에서 검수·공개·삭제 요청을 위해 처리돼요. 대기 {policy.pending_days}일·공개 {policy.public_days}일 후 만료, 매일 정리하며 백업은 제공자 정책상 최대 30일 남을 수 있어요. 서버 처리는 Vercel(서울)에서 수행해요. 자세한 국외 처리·삭제 방법은 위 안내에서 확인해 주세요.</Muted>
      {!receipt && !attempted ? <>
        <label style={inputStyle}>사진 파일 (JPEG·PNG·WebP, 2MB 이하)
          <input data-testid="visitor-file" type="file" accept="image/jpeg,image/png,image/webp" disabled={busy}
            style={inputStyle} onChange={e => { setError(null); setReady(false); setFaces(subject === 'self' ? [defaultBox()] : []);
              const next = e.target.files?.[0]; if (!next) { setFile(null); return; }
              if (next.size > policy.max_file_bytes) { setFile(null); setError('사진은 2MB 이하로 선택해 주세요.'); return; }
              setFile(next);
            }} />
        </label>
        <label style={inputStyle}>사진 속 인물
          <select aria-label="사진 속 인물" style={inputStyle} value={subject} onChange={e => {
            const value = e.target.value as 'space' | 'self'; setSubject(value); setFaces(value === 'self' ? [defaultBox()] : []);
            setChoice(old => ({ ...old, face_blur: false }));
          }}><option value="space">식별 가능한 인물이 없는 공간 사진</option><option value="self">본인이 나온 사진 · 얼굴 블러 필수</option></select>
        </label>
        {file ? <canvas ref={canvas} data-testid="visitor-preview" role="img" aria-label="블러 영역 미리보기. 제출 후 서버가 처리한 결과를 확인할 수 있어요." style={{ width: '100%', height: 'auto' }} /> : null}
        {faces.map((box, index) => <fieldset key={index} style={{ border: '1px solid ' + colors.line }}>
          <legend>얼굴 영역 {index + 1} · 사진 비율(%)</legend>
          {(['x', 'y', 'width', 'height'] as const).map(axis => {
            const names = { x: '왼쪽 위치', y: '위쪽 위치', width: '너비', height: '높이' };
            return <label key={axis} style={{ display: 'block', padding: 8 }}>{names[axis]} {Math.round(box[axis] * 100)}%
              <input type="range" aria-label={'얼굴 ' + (index + 1) + ' ' + names[axis]} min={axis === 'x' || axis === 'y' ? 0 : 4}
                max={100} value={Math.round(box[axis] * 100)} style={{ width: '100%', minHeight: 32 }}
                onChange={e => setFaces(old => old.map((b, i) => { if (i !== index) return b; const n = { ...b, [axis]: +e.target.value / 100 };
                  n.x = Math.min(n.x, 1 - n.width); n.y = Math.min(n.y, 1 - n.height); return n; }))} />
            </label>;
          })}
        </fieldset>)}
        {subject === 'self' ? <Button title="반사된 얼굴 영역 추가" variant="outline" disabled={faces.length >= 12} onPress={() => setFaces(old => [...old, defaultBox()])} /> : null}
        <Field label="공개할 이름 · 닉네임 (40자 이내)" value={credit} onChange={v => setCredit(v.slice(0, 40))} />
        <Field label="촬영 위치·구도 설명 (선택, 160자 이내)" value={caption} onChange={v => setCaption(v.slice(0, 160))} />
        <Muted size={12}>실명·연락처·생년월일을 적지 마세요. 원본은 저장하지 않으며 위치·기기정보를 지운 처리본만 보관해요.</Muted>
        {(Object.keys(labels) as (keyof Choice)[]).filter(k => k !== 'face_blur' || subject === 'self').map(k =>
          <Check key={k} name={k} checked={choice[k]} disabled={busy} onChange={() => setChoice(old => ({ ...old, [k]: !old[k] }))} />)}
      </> : null}
      {!receipt ? <Button title={attempted ? '같은 내용으로 접수 재시도' : '검수 요청 보내기'} loading={busy} disabled={!canSubmit && !attempted} onPress={() => void submit()} /> : null}
      {attempted && !receipt ? <Muted>응답이 끊겨도 중복 접수되지 않도록 같은 내용으로 재시도해요. 아래 관리 코드로 접수 여부를 먼저 확인할 수도 있어요.</Muted> : null}
      {sentPreview ? <><Body size={13}>서버에 보관된 처리본</Body><img src={sentPreview} alt="실제로 보관된 얼굴 블러 처리 사진" style={{ width: '100%', objectFit: 'contain' }} /></> : null}
      {previewError && receipt?.state === 'pending' ? <>
        <ErrorBox message="접수는 완료됐지만 처리본을 불러오지 못했어요. 사진을 다시 제출할 필요는 없어요." />
        <Button title="처리본 다시 보기" variant="outline" loading={previewBusy} onPress={() => { if (requestKey.current) void showStored(requestKey.current); }} />
      </> : null}
    </View> : null}
    <Button title={manage ? '접수 관리 접기' : '접수 상태 확인·철회'} variant="outline" onPress={() => setManage(!manage)} />
    {(manage || attempted) ? <View style={{ gap: 10 }}>
      <Field label="접수 관리 코드" value={code} onChange={setCode} />
      <Muted size={12}>이 코드를 가진 사람은 접수를 조회·철회할 수 있어요. 공유하지 말고 별도로 보관하세요. 계정·프로필이나 다른 기기로 자동 저장되지 않아요.</Muted>
      <Button title="접수 상태 확인" variant="outline" disabled={busy} onPress={() => void checkStatus()} />
      {receipt ? <View accessibilityLiveRegion="polite"><Body>{receiptState(receipt.state)}</Body>{receipt.note ? <Muted>{receipt.note}</Muted> : null}</View> : null}
      {receipt && receipt.state !== 'withdrawn' ? <Button title="사진 공개 요청 철회" variant="outline" disabled={busy} onPress={() => setConfirmWithdraw(true)} /> : null}
      {confirmWithdraw ? <><Muted>공개와 보관을 중단하고 사진을 삭제할까요?</Muted><Button title="철회하고 사진 삭제" disabled={busy} onPress={() => void checkStatus(true)} />
        <Button title="철회 취소" variant="outline" disabled={busy} onPress={() => setConfirmWithdraw(false)} /></> : null}
    </View> : null}
    {error ? <ErrorBox message={error} /> : null}
  </Card>;
}

