"""Score photo attributes and sourced space preferences; unknowns stay pending."""
import json
from pathlib import Path
from .score_display import ATTRIBUTES, GROUPS
from .labels import VALUE_LABELS

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'pipeline/data/matching_rules.json').read_text(encoding='utf-8'))
# Nominal weights total 100; the denominator is 80/90/100 (see SPARSE_EVIDENCE).
# Height and J/P do not contribute to place fit.
WEIGHTS = [
    {'dimension': dim, 'attribute': attr, 'weight': weight, 'layer': layer}
    for dim, attr, weight, layer in [
        ('pc_season', 'color_temp', 28, 'practical'),
        ('pc_tone', 'brightness', 6, 'practical'),
        ('pc_tone', 'saturation', 6, 'practical'),
        ('body_type', 'form', 30, 'practical'),
        ('mbti_ei', 'crowd_level', 10, 'auxiliary'),
        ('mbti_sn', 'place_character', 10, 'auxiliary'),
        ('mbti_tf', 'space_nature', 10, 'auxiliary'),
    ]
]
RULES = CONFIG['rules']
BASE_WEIGHT = sum(w['weight'] for w in WEIGHTS if w['dimension'] != 'element')
# 희소 지표는 프로필과 근거를 모두 갖춰 실제 평가할 때만 분모에 포함한다.
# 사진·지도 분류 지표는 근거가 없어도 기준에 남겨 한 항목 일치가 만점이 되지 않게 한다.
SPARSE_EVIDENCE = {'crowd_level', 'place_character'}


def catalog_card(profile):
    from . import services, schemas
    dims = dimensions(profile)
    rules = [r for r in RULES if r['dimension'] == 'pc_tone' and dims.get(r['dimension']) == r['user_value']]
    # 계절 → 빛 규칙(matching_rules.json pc_season/lighting). 결과 카드의 '잘 맞는 빛'과 피할 빛을 채운다.
    rules += [r for r in RULES if r['dimension'] == 'pc_season' and r['attribute'] == 'lighting' and dims.get('pc_season') == r['user_value']]
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
    if profile.get('mbti'): out.update(zip(('mbti_ei', 'mbti_sn', 'mbti_tf'), profile['mbti'][:3]))
    return out


DATA_REASONS = {
    'no_photo': '재사용 가능한 대표사진 없음',
    'analysis_pending': '현재 대표사진 색조 분석 대기',
    'cover_mismatch': '현재 대표사진과 이전 분석 근거 불일치 · 새 사진 분석 필요',
    'review_required': '대표사진 검토 필요 · 검토 전에는 점수에 반영하지 않아요',
    'insufficient_evidence': '판정에 충분한 근거 없음',
}


def explanation(profile, evidence, place=None, visitors=None, descriptions=None, *, photo_status=None):
    from .scoring_cache import scoring_features
    dims = dimensions(profile)
    attrs = dict(evidence.get('attributes', {})) if evidence else {}
    # Photo-only guesses cannot stand in for annual counts or source descriptions.
    for key in ('crowd_level', 'place_character', 'photo_mood', 'space_nature', 'setting'):
        attrs.pop(key, None)
    character, description_sources, nature, nature_note, nature_sources = scoring_features(place, descriptions)
    if character: attrs['place_character'] = character
    if nature: attrs['space_nature'] = nature
    if visitors and visitors['status'] == 'ranked':
        attrs['crowd_level'] = 'ranked'
    if attrs.get('form') == 'organic':
        attrs.pop('form')  # old natural-scene tag is not proof of straight lines
    photo_status = 'ready' if evidence else photo_status or 'analysis_pending'
    metrics, raw, evaluated_weight = [], 0, 0
    for weight in WEIGHTS:
        dim, attr, w = weight['dimension'], weight['attribute'], weight['weight']
        if dim == 'element': continue  # Saju is a separate, sourced filter.
        group = next(label for label, ds in GROUPS.values() if dim in ds)
        status = 'missing_input' if dim not in dims else 'pending' if attr not in attrs else 'scored'
        data_status = 'ready' if attr in attrs else 'insufficient_evidence'
        if attr not in attrs and attr in {'color_temp', 'brightness', 'saturation', 'form'}:
            data_status = photo_status if photo_status != 'ready' else 'analysis_pending'
            if attr == 'form' and photo_status == 'ready':
                from pipeline.catalog_visuals import REVIEWS
                review = REVIEWS.get((place or {}).get('id'))
                reviewed = review and (review['photo_url'], review['source_url']) == (evidence['photo_url'], evidence['source_url'])
                data_status = 'insufficient_evidence' if reviewed else 'review_required'
        score = None
        sources = description_sources if attr == 'place_character' else nature_sources if attr == 'space_nature' else []
        note = '프로필 입력 필요' if status == 'missing_input' else '사진·현장 근거 확인 전'
        if status == 'scored':
            value = attrs[attr]
            note = '사진에서 확인: ' + VALUE_LABELS.get(attr, {}).get(value, value)
            if attr == 'form':
                expected = {'wave': 'curved', 'natural': 'linear', 'straight': 'volumetric'}[dims[dim]]
                factor = float(value == expected)
                method = '사진 윤곽 자동 추정' if evidence and 'photo-geometry-' in evidence.get('method', '') else '사진 검토'
                note = f"{method}: {VALUE_LABELS['form'][value]} · {VALUE_LABELS['form'][expected]} 선호"
                from pipeline.catalog_visuals import REVIEWS
                review = REVIEWS.get((place or {}).get('id'))
                if review and evidence and (review['photo_url'], review['source_url']) == (evidence.get('photo_url'), evidence.get('source_url')):
                    if review.get('note'): note += ' · ' + review['note']
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
            elif attr == 'place_character':
                target = 'detail' if dims[dim] == 'S' else 'concept'
                factor = .5 if value == 'mixed' else float(value == target)
                words = sorted({word for source in sources for word in source['keywords']})
                note = '공간 설명·평가 문구: ' + ' · '.join(words) + (' · 두 성격 모두 확인, 중립' if value == 'mixed' else '')
            elif attr == 'space_nature':
                factor = .5 if value == 'mixed' else float(value == ('architecture' if dims[dim] == 'T' else 'nature'))
                note = nature_note + ' · ' + ('건축 공간 선호' if dims[dim] == 'T' else '자연 공간 선호')
            else:
                matches = [r['score'] for r in RULES if r['dimension'] == dim and r['user_value'] == dims[dim]
                           and r['attribute'] == attr and r['attr_value'] == value]
                factor = max(matches, default=0)
                if attr == 'brightness':
                    note += ' · 사진 픽셀의 밝기·대비이며 현장 조도 실측값이 아니에요'
                elif attr == 'saturation':
                    note += ' · 해당 사진의 채도이며 보정·촬영 조건에 따라 달라져요'
            score = round(factor * w, 4)
            raw += score
            evaluated_weight += w
        elif status == 'pending' and attr == 'crowd_level':
            period = f"{visitors['period_start']}~{visitors['period_end']} " if visitors else ''
            note = period + ('비교 가능한 장소가 2곳 미만이에요' if visitors and visitors['status'] == 'insufficient' else '2025년 연간 입장객 수 미집계')
        elif status == 'pending' and attr == 'form':
            note = '사진 형태 분석 근거 부족 · 직선·곡선·큰 형체를 확인하지 못했어요'
        elif status == 'pending' and attr == 'place_character':
            note = '검토한 공간 설명에 판정 문구 없음' if description_sources else '출처가 확인된 공간 설명 근거 확인 전'
        elif status == 'pending' and attr == 'space_nature':
            note = '건축물·자연물 공간 분류 근거 부족'
        if status == 'pending' and attr in {'color_temp', 'brightness', 'saturation', 'form'}:
            note = DATA_REASONS[data_status]
            if attr == 'form' and data_status == 'review_required':
                note += ' · 직선·곡선·큰 형체의 자동 후보는 검토 후 반영해요'
        attr_label = '사진 색조' if attr == 'color_temp' else ATTRIBUTES[attr]
        metrics.append({'key': f'{dim}.{attr}', 'label': f'{group} · {attr_label}', 'weight': w,
                        'points': score, 'maximum': w if score is not None else None, 'status': status,
                        'note': note, 'sources': sources, 'evidence_status': data_status})
    # A single matching metric must not become a perfect overall score. Missing
    # inputs/evidence keep their status and remain part of the basis, except the
    # sparse metrics above, which count only when both input and evidence exist.
    basis = BASE_WEIGHT - sum(m['weight'] for m in metrics if m['status'] != 'scored' and m['key'].split('.')[1] in SPARSE_EVIDENCE)
    score = round(max(0, min(100, raw / basis * 100)), 1) if evaluated_weight else None
    return {'basis': 'photo' if evidence else 'category', 'score': score, 'metrics': metrics,
            'note': f'획득 배점의 합계를 기본 배점 {basis:g}점으로 나누어 100점으로 환산해요. '
                    '미평가·미입력 항목도 배점에 포함하되, 방문객·공간 설명 지표는 프로필과 근거가 모두 있어 평가할 때만 각각 10점을 넣어요(분모 80·90·100점). '
                    '확인 전에는 점수를 더하지 않고, 지도 분류로 추정한 항목은 추정으로 표시해요. 목록은 표시된 전체 정합도 순으로 정렬해요. '
                    '미평가는 부적합 판정이 아니며, 오행·일진은 별도로 평가해요.',
            'evaluated_weight': evaluated_weight, 'total_weight': basis,
            'evidence_ready_count': sum(m['evidence_status'] == 'ready' for m in metrics),
            'evidence_weight': sum(m['weight'] for m in metrics if m['evidence_status'] == 'ready'),
            'preference_score': round(max(0, min(100, raw / evaluated_weight * 100)), 1) if evaluated_weight else None,
            'evidence_url': evidence.get('source_url') if evidence else None,
            'evidence_method': evidence.get('method') if evidence else None,
            'visitor_context': visitors}
