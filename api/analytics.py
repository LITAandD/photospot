"""First-party optional usage events: allowlisted names, an anonymous client session id, no PII.

Events land in the likes PostgreSQL (analytics_events) when it is configured and
reachable; otherwise the client gets 503 and structured logs report the failure. Routes are
paths only (no query strings), UTM keys are fixed, props are small scalars.
"""
from typing import Literal
import logging

from pydantic import BaseModel, ConfigDict, Field, field_validator
from psycopg.types.json import Jsonb

from . import photo_likes

EVENTS = ('landing_view', 'home_first_card', 'result_view', 'share_click', 'place_view', 'save',
          'consent_accept', 'gps_allow', 'client_error', 'recommendation_request', 'recommendation_result',
          'card_impression', 'map_open', 'empty_result', 'recommendation_error')  # client_error: kind/operation only; no raw error text from v2 clients
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
