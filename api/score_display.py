"""Expose configured weights and complete score contributions, including zero/negative values."""
GROUPS = {
    'personal_color': ('퍼스널컬러', {'pc_season', 'pc_tone'}),
    'body_type': ('체형', {'body_type'}),
    'height': ('키', {'height_band'}),
    'mbti': ('MBTI', {'mbti_ei', 'mbti_sn', 'mbti_tf'}),
    'element': ('보완 오행', {'element'}),
    'day_element': ('일진', {'day_element'}),
}
ATTRIBUTES = {'lighting': '조명', 'color_temp': '색온도', 'brightness': '명도', 'saturation': '채도', 'setting': '실내·야외',
              'form': '형태', 'texture': '질감', 'scale': '공간 규모', 'crowd_level': 'E/I · 2025 방문객',
              'place_character': 'S/N · 공간 설명', 'space_nature': 'T/F · 건축·자연', 'photo_mood': '사진 분위기', 'element': '오행 대응'}
DAY_WEIGHT = {'dimension': 'day_element', 'attribute': 'element', 'weight': 4, 'layer': 'auxiliary'}


def with_day(weights):
    return [*weights, DAY_WEIGHT]


def weight_guide(weights):
    result = []
    for key, (label, dimensions) in GROUPS.items():
        rows = [w for w in with_day(weights) if w['dimension'] in dimensions]
        if not rows:
            continue
        result.append({'key': key, 'label': label, 'weight': sum(float(w['weight']) for w in rows),
                       'detail': ' · '.join(f"{ATTRIBUTES[w['attribute']]} {float(w['weight']):g}" for w in rows),
                       'optional': key in {'element', 'day_element'}})
    return result


def photo_explanation(weights, breakdown, score):
    metrics = []
    for w in with_day(weights):
        dim, attr, maximum = w['dimension'], w['attribute'], float(w['weight'])
        key = f'{dim}.{attr}'
        group = next(label for label, dimensions in GROUPS.values() if dim in dimensions)
        present = key in breakdown
        optional = dim in {'element', 'day_element'}
        metrics.append({'key': key, 'label': f'{group} · {ATTRIBUTES[attr]}', 'weight': maximum,
                        'points': float(breakdown[key]) if present else None, 'maximum': maximum,
                        'status': 'scored' if present else 'optional' if optional else 'missing_input',
                        'note': '' if present else '추가 추천에서 조건에 맞을 때 반영' if optional else '프로필 입력 필요'})
    return {'basis': 'photo', 'score': float(score) if breakdown else None, 'metrics': metrics,
            'note': '항목별 기여 점수를 합산한 뒤 적용된 가중치 합으로 나누어 100점으로 환산해요. 감점과 0점도 함께 표시해요.'}
