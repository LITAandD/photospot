from api.score_display import weight_guide, photo_explanation
from api.schemas import ScoreExplanation

# Version 1 rows of score_weights as seeded by schema.sql.
WEIGHTS = [dict(zip(['version', 'dimension', 'attribute', 'layer', 'weight'], row)) for row in [
    (1, 'pc_season', 'lighting', 'practical', 16), (1, 'pc_season', 'color_temp', 'practical', 12),
    (1, 'pc_tone', 'brightness', 'practical', 6), (1, 'pc_tone', 'saturation', 'practical', 6),
    (1, 'body_type', 'form', 'practical', 15), (1, 'body_type', 'texture', 'practical', 15),
    (1, 'height_band', 'scale', 'practical', 10), (1, 'mbti_ei', 'crowd_level', 'auxiliary', 4),
    (1, 'mbti_sn', 'place_character', 'auxiliary', 4), (1, 'mbti_tf', 'photo_mood', 'auxiliary', 4),
    (1, 'element', 'element', 'auxiliary', 8)]]


def test_original_weights_are_read_from_the_scoring_configuration():
    guide = weight_guide(WEIGHTS)
    assert [(w['label'], w['weight']) for w in guide] == [
        ('퍼스널컬러', 40), ('체형', 30), ('키', 10), ('MBTI', 12), ('보완 오행', 8), ('일진', 4)]
    assert [w['key'] for w in guide if w['optional']] == ['element', 'day_element']
    assert guide[0]['detail'] == '조명 16 · 색온도 12 · 명도 6 · 채도 6'
    changed = [{**w, 'weight': 20 if w['attribute'] == 'lighting' else w['weight']} for w in WEIGHTS]
    assert weight_guide(changed)[0]['weight'] == 44


def test_photo_breakdown_preserves_zero_negative_and_missing_contributions():
    raw = {'pc_season.lighting': 16, 'pc_season.color_temp': -12, 'mbti_tf.photo_mood': 0}
    output = ScoreExplanation.model_validate(photo_explanation(WEIGHTS, raw, 12.5))
    rows = {r.key: r for r in output.metrics}
    assert output.score == 12.5
    assert rows['pc_season.color_temp'].points == -12
    assert rows['mbti_tf.photo_mood'].points == 0 and rows['mbti_tf.photo_mood'].status == 'scored'
    assert rows['body_type.form'].points is None and rows['body_type.form'].status == 'missing_input'
    assert rows['element.element'].status == rows['day_element.element'].status == 'optional'
    assert len(output.metrics) == 12
    assert photo_explanation(WEIGHTS, {}, 0)['score'] is None
