from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class FeedbackSubmission(BaseModel):
    category: Literal['bug', 'idea', 'place', 'other']
    message: str = Field(min_length=5, max_length=2000)
    ai_consent: bool = False

    @field_validator('message')
    @classmethod
    def strip_message(cls, value):
        value = value.strip()
        if len(value) < 5: raise ValueError('의견을 5자 이상 입력해 주세요')
        return value

class FeedbackOut(FeedbackSubmission):
    id: UUID
    created_at: datetime
    reviewed_text: str | None = None

class FeedbackReview(BaseModel):
    reviewed_text: str = Field(min_length=5, max_length=2000)

class TriageBatch(BaseModel):
    feedback_ids: list[UUID] = Field(min_length=1, max_length=20)

class TriageIdea(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=1200)
    feedback_ids: list[str] = Field(min_length=1, max_length=20)
    impact: int = Field(ge=1, le=5)
    urgency: int = Field(ge=1, le=5)
    effort: int = Field(ge=1, le=5)
    reason: str = Field(min_length=1, max_length=800)
    acceptance: str = Field(min_length=1, max_length=1200)

class TriageResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ideas: list[TriageIdea] = Field(min_length=1, max_length=20)

class TriageDecision(BaseModel):
    status: Literal['approved', 'planned', 'done', 'dismissed']
    note: str = Field(min_length=3, max_length=1000)

class CampaignIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    place_id: UUID
    sponsor: str = Field(min_length=1, max_length=80)
    headline: str = Field(min_length=1, max_length=100)
    placement: Literal['banner', 'priority']
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode='after')
    def dates(self):
        if not self.starts_at.tzinfo or not self.ends_at.tzinfo or self.ends_at <= self.starts_at:
            raise ValueError('시간대가 포함된 유효한 광고 기간을 입력해 주세요')
        if (self.ends_at - self.starts_at).days > 366: raise ValueError('광고 기간은 최대 1년이에요')
        return self

class CampaignApproval(BaseModel):
    approved: bool

class CampaignEvent(BaseModel):
    kind: Literal['impression', 'click']

class BillingStatus(BaseModel):
    user_id: str
    premium: bool
    premium_until: datetime | None = None
    management_url: str | None = None
    configured: bool

class GrowthSession(BaseModel):
    user_id: str
    is_admin: bool
    instagram_configured: bool
    billing_configured: bool
    ai_configured: bool
