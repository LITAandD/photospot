"""Korean validation summaries without reflecting input values or exceptions."""

LABELS = {'birth_date': '생년월일', 'birth_time': '태어난 시간', 'birth_year': '출생연도',
          'height_cm': '키', 'lat': '위도', 'lng': '경도', 'radius_m': '검색 반경',
          'visit_date': '촬영일', 'date': '촬영일', 'consent': '정보 사용 동의',
          'place_ids': '장소 목록', 'limit': '조회 개수', 'mbti': 'MBTI'}


def validation_detail(errors):
    messages = []
    for error in errors:
        label = next((LABELS[key] for key in reversed(error['loc']) if key in LABELS), '입력값')
        kind = error['type']
        if kind == 'missing':
            message = '필수 항목이에요'
        elif kind in {'greater_than', 'greater_than_equal', 'less_than', 'less_than_equal', 'too_long', 'too_short'}:
            message = '허용 범위와 길이를 확인해 주세요'
        elif kind in {'enum', 'literal_error'}:
            message = '선택할 수 있는 값인지 확인해 주세요'
        else:
            message = '형식과 내용을 확인해 주세요'
        summary = f'{label}: {message}'
        if summary not in messages:
            messages.append(summary)
    return '; '.join(messages)
