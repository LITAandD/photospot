"""Score only observed photo attributes; unknowns never become invented matches."""
import json
from pathlib import Path
from .score_display import ATTRIBUTES, GROUPS
from .labels import VALUE_LABELS

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'pipeline/data/matching_rules.json').read_text(encoding='utf-8'))
# Catalog v2 combines overlapping color/lighting and body/texture weights.
# The legacy PostGIS scene rules stay versioned separately.
WEIGHTS = [{**w, 'attribute': 'setting' if w['attribute'] == 'scale' else w['attribute'],
            'weight': 28 if w['attribute'] == 'color_temp' else 30 if w['attribute'] == 'form' else w['weight']}
           for w in CONFIG['weights'] if w['attribute'] not in {'lighting', 'texture'}]
RULES = CONFIG['rules']
BASE_WEIGHT = sum(w['weight'] for w in WEIGHTS if w['dimension'] != 'element')


def catalog_card(profile):
    from . import services, schemas
    dims = dimensions(profile)
    rules = [r for r in RULES if r['dimension'] == 'pc_tone' and dims.get(r['dimension']) == r['user_value']]
    body = profile.get('body_type')
    if body:
        rules.append({'attribute': 'form', 'attr_value': {'wave': 'curved', 'natural': 'linear', 'straight': 'volumetric'}[body], 'score': 1})
    if profile.get('pc_season'):
        rules.append({'attribute': 'color_temp', 'attr_value': 'warm' if profile['pc_season'].endswith('warm') else 'cool', 'score': 1})
    return schemas.TypeCard.model_validate(services.type_card(profile, None, rules))


def dimensions(profile):
    out = {key: profile[key] for key in ('pc_season', 'body_type') if profile.get(key)}
    if profile.get('pc_season'):
        tone = profile.get('pc_subtone')
        out['pc_tone'] = tone if tone and tone != 'true' else 'default_' + profile['pc_season']
    if profile.get('height_cm'):
        out['height_band'] = 'small' if profile['height_cm'] < 170 else 'tall' if profile['height_cm'] > 170 else 'medium'
    if profile.get('mbti'): out.update(zip(('mbti_ei', 'mbti_sn', 'mbti_tf'), profile['mbti'][:3]))
    return out


def place_setting(place, attrs):
    if attrs.get('setting') in {'indoor', 'outdoor', 'mixed'}:
        return attrs['setting'], '사진 검토'
    if not place:
        return None, ''
    # Describe the venue's use, not the photographed facade. Mixed/unknown
    # attractions and heritage sites are not silently treated as outdoor.
    tags = place.get('tags') or {}
    if isinstance(tags, str):
        tags = json.loads(tags)
    if tags.get('indoor') in {'yes', 'no'}:
        return ('indoor' if tags['indoor'] == 'yes' else 'outdoor'), '지도 실내외 정보'
    kind = place.get('category')
    if kind in {'cafe', 'museum', 'gallery', 'event_venue', 'cultural_venue'}:
        if tags.get('outdoor_seating') == 'yes':
            return 'mixed', '장소 유형·야외 좌석 정보'
        return 'indoor', '장소 유형 기준 추정'
    if kind in {'park', 'waterfront', 'scenic'}:
        return 'outdoor', '장소 유형 기준 추정'
    return None, ''


def explanation(profile, evidence, place=None, visitors=None):
    dims = dimensions(profile)
    attrs = dict(evidence.get('attributes', {})) if evidence else {}
    # A photograph's visible people are never a three-month crowd observation.
    attrs.pop('crowd_level', None)
    setting, setting_method = place_setting(place, attrs)
    if setting:
        attrs['setting'] = setting
    if visitors and visitors['status'] == 'ranked':
        attrs['crowd_level'] = 'ranked'
    if attrs.get('form') == 'organic':
        attrs.pop('form')  # old natural-scene tag is not proof of straight lines
    metrics, raw, denominator = [], 0, 0
    for weight in WEIGHTS:
        dim, attr, w = weight['dimension'], weight['attribute'], weight['weight']
        if dim == 'element': continue  # Saju is a separate, sourced filter.
        group = next(label for label, ds in GROUPS.values() if dim in ds)
        status = 'missing_input' if dim not in dims else 'pending' if attr not in attrs else 'scored'
        score = None
        note = '프로필 입력 필요' if status == 'missing_input' else '사진·현장 근거 확인 전'
        if status == 'scored':
            value = attrs[attr]
            note = '사진에서 확인: ' + VALUE_LABELS.get(attr, {}).get(value, value)
            if attr == 'form':
                expected = {'wave': 'curved', 'natural': 'linear', 'straight': 'volumetric'}[dims[dim]]
                factor = float(value == expected)
                method = '사진 윤곽 자동 추정' if evidence and 'photo-geometry-' in evidence.get('method', '') else '사진 검토'
                note = f"{method}: {VALUE_LABELS['form'][value]} · {VALUE_LABELS['form'][expected]} 선호"
            elif attr == 'setting':
                factor = .5 if dims[dim] == 'medium' or value == 'mixed' else float(value == ('outdoor' if dims[dim] == 'tall' else 'indoor'))
                preference = '170cm · 실내외 중립' if dims[dim] == 'medium' else ('170cm 초과 · 야외 선호' if dims[dim] == 'tall' else '170cm 미만 · 실내 선호')
                note = f"{setting_method}: {VALUE_LABELS['setting'][value]} · {preference}"
            elif attr == 'color_temp':
                target = 'warm' if dims[dim].endswith('warm') else 'cool'
                factor = .5 if value == 'neutral' else float(value == target)
                note = f"사진 색조 분석: {VALUE_LABELS[attr][value]} · {'웜톤' if target == 'warm' else '쿨톤'} 선호 (실측 조명 온도 아님)"
            elif attr == 'crowd_level':
                p = visitors['percentile']
                factor = p if dims[dim] == 'E' else 1 - p
                preference = '방문객 많은 곳 선호' if dims[dim] == 'E' else '방문객 적은 곳 선호'
                note = (f"{visitors['period_start']}~{visitors['period_end']} 합계 {visitors['visitors']:,}명 · "
                        f"집계 {visitors['measured_count']:,}곳 중 {visitors['rank']:,}위 · {preference}. 실시간 밀집도와는 달라요.")
            else:
                matches = [r['score'] for r in RULES if r['dimension'] == dim and r['user_value'] == dims[dim]
                           and r['attribute'] == attr and r['attr_value'] == value]
                factor = max(matches, default=0)
            score = round(factor * w, 4)
            raw += score
            denominator += w
        elif status == 'pending' and attr == 'crowd_level':
            period = f"{visitors['period_start']}~{visitors['period_end']} " if visitors else ''
            note = period + ('비교 가능한 장소가 2곳 미만이에요' if visitors and visitors['status'] == 'insufficient' else '장소별 3개월 방문객 수 미집계')
        elif status == 'pending' and attr == 'form':
            note = '사진 형태 분석 근거 부족 · 직선·곡선·큰 형체를 확인하지 못했어요'
        elif status == 'pending' and attr == 'setting':
            note = '실내외 이용 공간 정보 확인 전'
        attr_label = '조명·배경 색조' if attr == 'color_temp' else ATTRIBUTES[attr]
        metrics.append({'key': f'{dim}.{attr}', 'label': f'{group} · {attr_label}', 'weight': w,
                        'points': score, 'maximum': w if score is not None else None, 'status': status,
                        'note': note})
    score = round(max(0, min(100, raw / denominator * 100)), 1) if denominator else None
    return {'basis': 'photo', 'score': score, 'metrics': metrics,
            'note': f'평가 가능한 항목 {denominator:g}/{BASE_WEIGHT:g} 가중치로 계산해 100점으로 환산해요. '
                    '사진 색조·형태, 실내외 공간, 최근 완료된 3개월 방문객 수를 사용하는 취향 참고 기준이에요. 미집계·미평가는 제외해요.',
            'evaluated_weight': denominator, 'total_weight': BASE_WEIGHT,
            'evidence_url': evidence.get('source_url') if evidence else None,
            'evidence_method': evidence.get('method') if evidence else None,
            'visitor_context': visitors}
