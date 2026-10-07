"""Score only observed photo attributes; unknowns never become invented matches."""
import json
from pathlib import Path
from .score_display import ATTRIBUTES, GROUPS
from .labels import VALUE_LABELS

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'pipeline/data/matching_rules.json').read_text(encoding='utf-8'))
WEIGHTS, RULES = CONFIG['weights'], CONFIG['rules']
BASE_WEIGHT = sum(w['weight'] for w in WEIGHTS if w['dimension'] != 'element')


def dimensions(profile):
    out = {key: profile[key] for key in ('pc_season', 'body_type') if profile.get(key)}
    if profile.get('pc_season'):
        tone = profile.get('pc_subtone')
        out['pc_tone'] = tone if tone and tone != 'true' else 'default_' + profile['pc_season']
    if profile.get('height_cm'):
        low, high = {'female': (157, 167), 'male': (170, 180)}.get(profile.get('gender'), (163, 174))
        out['height_band'] = 'small' if profile['height_cm'] < low else 'tall' if profile['height_cm'] >= high else 'medium'
    if profile.get('mbti'): out.update(zip(('mbti_ei', 'mbti_sn', 'mbti_tf'), profile['mbti'][:3]))
    return out


def explanation(profile, evidence):
    dims = dimensions(profile)
    attrs = evidence.get('attributes', {}) if evidence else {}
    metrics, raw, denominator = [], 0, 0
    for weight in WEIGHTS:
        dim, attr, w = weight['dimension'], weight['attribute'], weight['weight']
        if dim == 'element': continue  # Saju is a separate, sourced filter.
        group = next(label for label, ds in GROUPS.values() if dim in ds)
        status = 'missing_input' if dim not in dims else 'pending' if attr not in attrs else 'scored'
        score = None
        if status == 'scored':
            matches = [r['score'] for r in RULES if r['dimension'] == dim and r['user_value'] == dims[dim]
                       and r['attribute'] == attr and r['attr_value'] == attrs[attr]]
            score = max(matches, default=0) * w
            raw += score
            denominator += w
        metrics.append({'key': f'{dim}.{attr}', 'label': f'{group} · {ATTRIBUTES[attr]}', 'weight': w,
                        'points': score, 'maximum': w if score is not None else None, 'status': status,
                        'note': ('사진에서 확인: ' + VALUE_LABELS.get(attr, {}).get(attrs[attr], attrs[attr])) if status == 'scored' else
                                '프로필 입력 필요' if status == 'missing_input' else '사진·현장 근거 확인 전'})
    score = round(max(0, min(100, raw / denominator * 100)), 1) if denominator else None
    return {'basis': 'photo', 'score': score, 'metrics': metrics,
            'note': f'확인된 사진 항목 {denominator:g}/{BASE_WEIGHT:g} 가중치로 계산해 100점으로 환산해요. '
                    '미평가 항목은 제외하며, 사진 촬영 당시의 색과 공간을 기준으로 한 취향 참고 점수예요.',
            'evaluated_weight': denominator, 'total_weight': BASE_WEIGHT,
            'evidence_url': evidence.get('source_url') if evidence else None,
            'evidence_method': evidence.get('method') if evidence else None}
