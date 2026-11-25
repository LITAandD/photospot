"""First-party optional usage events: allowlisted names, an anonymous client session id, no PII.

Events land in the likes PostgreSQL (analytics_events) when it is configured and
reachable; otherwise the client gets 503 and structured logs report the failure. Routes are
paths only (no query strings), UTM keys are fixed, props are small scalars.
"""
from typing import Literal
import logging

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from psycopg.types.json import Jsonb

from . import photo_likes

EVENTS = ('landing_view', 'home_first_card', 'result_view', 'share_click', 'place_view', 'save',
          'consent_accept', 'gps_allow', 'client_error', 'recommendation_request', 'recommendation_result',
          'card_impression', 'map_open', 'empty_result', 'recommendation_error',
          'shot_directions', 'shot_alternative', 'shot_completed', 'shot_view')  # shot events never include position or photos
UTM_KEYS = frozenset({'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'})
MAX_BODY_BYTES = 4096
MAX_PROPS = 20


class EventIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event: Literal[EVENTS]  # type: ignore[valid-type]
    route: str = Field(pattern=r'^/[^\s?#]{0,119}$')
    session_id: str = Field(pattern=r'^[A-Za-z0-9_-]{8,64}$')
    utm: dict[str, str] = Field(default_factory=dict)
    props: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode='after')
    def shot_fields(self):
        if self.event.startswith('shot_') or self.event == 'share_click' and self.props.get('surface') == 'today_shot':
            import re
            common = {'cut_id', 'schema_version', 'traffic'}
            specific = {
                'shot_view': {'result'}, 'shot_directions': {'provider','outcome'},
                'shot_alternative': {'from_cut_id','outcome'}, 'shot_completed': {'outcome'},
                'share_click': {'surface','outcome'},
            }[self.event]
            if set(self.props) - common - specific:
                raise ValueError('촬영 안내 이벤트에는 좌표·사진·프로필·조회 조건을 보낼 수 없어요')
            def valid_id(value):
                return isinstance(value, str) and not value.startswith('test-') and re.fullmatch(r'[a-z0-9][a-z0-9-]{2,63}', value)
            cut = self.props.get('cut_id')
            if self.event == 'shot_view':
                result = self.props.get('result')
                if result not in ('primary','alternative_available','empty') or (result == 'empty' and cut is not None) or (result != 'empty' and not valid_id(cut)):
                    raise ValueError('조회 결과와 컷 식별자를 확인해 주세요')
            elif not valid_id(cut):
                raise ValueError('컷 식별자를 확인해 주세요')
            expected = {'shot_directions':'opened','shot_alternative':'opened','shot_completed':'reported'}
            if self.event in expected and self.props.get('outcome') != expected[self.event]:
                raise ValueError('이벤트 결과를 확인해 주세요')
            if self.event == 'shot_directions' and self.props.get('provider') not in ('kakao','naver','google'):
                raise ValueError('지도 제공자를 확인해 주세요')
            if self.event == 'shot_alternative' and not valid_id(self.props.get('from_cut_id')):
                raise ValueError('교체 전 컷 식별자를 확인해 주세요')
            if self.event == 'share_click' and self.props.get('outcome') not in ('shared','copied','dismissed','failed'):
                raise ValueError('공유 결과를 확인해 주세요')
        return self

    @field_validator('utm')
    @classmethod
    def known_utm(cls, value):
        if set(value) - UTM_KEYS or any(len(v) > 100 for v in value.values()):
            raise ValueError('utm 값을 확인해 주세요')
        return value

    @field_validator('props')
    @classmethod
    def small_props(cls, value):
        if (len(value) > MAX_PROPS or any(not k.isidentifier() or len(k) > 40 for k in value)
                or any(isinstance(v, str) and len(v) > 200 for v in value.values())):
            raise ValueError('props 값을 확인해 주세요')
        return value


def store(event):
    """True when persisted; False when no store is configured or it is unavailable."""
    if not photo_likes.available():
        return False
    try:
        with photo_likes.connection(timeout=photo_likes.READ_TIMEOUT_S) as conn:
            conn.execute('INSERT INTO analytics_events (event, route, session_id, utm, props) VALUES (%s,%s,%s,%s,%s)',
                         (event['event'], event['route'], event['session_id'], Jsonb(event['utm']), Jsonb(event['props'])))
    except photo_likes.STORE_ERRORS:
        logging.getLogger(__name__).warning('analytics_store_failed')
        return False
    return True
