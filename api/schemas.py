"""요청·응답 모델. 이 정의에서 OpenAPI 명세가 자동 생성된다."""
from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from uuid import UUID

Gender = Literal["female", "male", "other", "undisclosed"]
Season = Literal["spring_warm", "summer_cool", "autumn_warm", "winter_cool"]
Subtone = Literal["light", "bright", "true", "mute", "deep"]
Body = Literal["straight", "wave", "natural"]
TimeSlot = Literal["morning", "midday", "golden_hour", "night"]
ConsentType = Literal["style_profile", "saju", "photo_analysis", "location"]
Element = Literal["wood", "fire", "earth", "metal", "water"]
BirthHourBranch = Literal["zi", "chou", "yin", "mao", "chen", "si", "wu", "wei", "shen", "you", "xu", "hai"]
PlaceGroup = Literal["all", "cafe", "travel", "festival"]


class Problem(BaseModel):
    """오류 응답 (RFC 9457 형식)."""
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None


# --- 프로필 -----------------------------------------------------------------
class Profile(BaseModel):
    gender: Gender = "undisclosed"
    birth_year: int | None = Field(None, ge=1900, le=2100)
    height_cm: float | None = Field(None, ge=100, le=230)
    pc_season: Season | None = None
    pc_subtone: Subtone | None = None
    body_type: Body | None = None
    mbti: str | None = Field(None, pattern=r"^[EI][SN][TF][JP]$")

    @field_validator("birth_year")
    @classmethod
    def valid_birth_year(cls, value):
        if value is not None and value > date.today().year:
            raise ValueError("출생연도는 올해보다 클 수 없어요")
        return value

    @model_validator(mode="after")
    def valid_subtone(self):
        if self.pc_subtone and not self.pc_season:
            raise ValueError("세부 톤을 고르려면 퍼스널컬러를 먼저 선택해 주세요")
        return self


class ProfileOut(Profile):
    profile_exists: bool = False
    height_band: Literal["small", "medium", "tall"] | None = None
    saju_enabled: bool = False
    saju_element: Element | None = None
    saju_percents: dict[Element, float] | None = None


class SajuIn(BaseModel):
    birth_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="선택한 달력의 YYYY-MM-DD. 음력 2월 30일도 지원")
    birth_time: time | None = Field(None, description="모르면 비워두면 년·월·일 6글자로 계산")
    birth_hour_branch: BirthHourBranch | None = Field(None, description="자·축·인·묘·진·사·오·미·신·유·술·해. 직접 시지 선택, birth_time과 동시 입력 불가")
    calendar: Literal["solar", "lunar"] = "solar"
    leap_month: bool = Field(False, description="음력 윤달 출생이면 true")
    consent: bool = Field(..., description="true여야 계산. 원본은 계산 직후 폐기되고 저장되지 않음")

    @field_validator("birth_date", mode="before")
    @classmethod
    def normalize_birth_date(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if len(value) == 8 and value.isascii() and value.isdigit():
                return f"{value[:4]}-{value[4:6]}-{value[6:]}"
        return value

    @model_validator(mode="after")
    def valid_birth(self):
        if self.birth_time is not None and self.birth_hour_branch is not None:
            raise ValueError("태어난 시각과 12지시 중 하나만 선택해 주세요")
        from saju.calculator import lunar_to_solar
        solar = lunar_to_solar(self.birth_date, self.leap_month) if self.calendar == "lunar" else date.fromisoformat(self.birth_date)
        if solar.year < 1900 or solar > date.today():
            raise ValueError("생년월일은 1900년부터 오늘 사이로 입력해 주세요")
        if self.leap_month and self.calendar != "lunar":
            raise ValueError("윤달은 음력에서만 선택할 수 있어요")
        if self.birth_time and self.birth_time.tzinfo:
            raise ValueError("태어난 시간은 한국 현지 시각으로 입력해 주세요")
        return self


class PillarOut(BaseModel):
    hanja: str
    hangul: str


class SajuOut(BaseModel):
    method: str = Field(description="forceteller_v1: 궁성·조후 보정(포스텔러 방식) + 합충 보정")
    percents: dict[Element, float] = Field(description="오행 비율(%)")
    dominant_element: Element = Field(description="가장 많은 오행 — 추천에 쓰는 값")
    dominant_label: str
    pillars: dict[str, PillarOut] = Field(description="년·월·일·(시)주. 표시용이며 저장하지 않음")
    corrections: list[str] = Field(description="적용된 합충·조후 보정 내역")
    has_birth_time: bool


class ConsentIn(BaseModel):
    type: ConsentType


class TypeCard(BaseModel):
    name: str
    subtitle: str
    best_light: list[str]
    good_backgrounds: list[str]
    avoid: list[str]
    lucky: str | None = None


# --- 추천 -------------------------------------------------------------------
class Reason(BaseModel):
    label: str
    points: float
    layer: Literal["practical", "auxiliary"]


class ScoreWeight(BaseModel):
    key: str
    label: str
    weight: float
    detail: str
    optional: bool = False


class ScoreMetric(BaseModel):
    key: str
    label: str
    points: float | None
    maximum: float | None
    weight: float
    status: Literal["scored", "missing_input", "pending", "optional"]
    note: str = ""


class VisitorSource(BaseModel):
    url: str
    label: str


class VisitorContext(BaseModel):
    period_start: str
    period_end: str
    as_of: str
    catalog_count: int
    measured_count: int
    status: Literal['ranked', 'unavailable', 'insufficient']
    rank: int | None = None
    visitors: int | None = None
    percentile: float | None = None
    sources: list[VisitorSource] = Field(default_factory=list)


class ScoreExplanation(BaseModel):
    basis: Literal["category", "photo"]
    score: float | None
    note: str
    metrics: list[ScoreMetric]
    evaluated_weight: float | None = None
    total_weight: float | None = None
    evidence_url: str | None = None
    evidence_method: str | None = None
    visitor_context: VisitorContext | None = None


class Photo(BaseModel):
    url: str
    attribution: str
    license: str
    keep_aspect_ratio: bool = Field(..., description="공공누리 3유형(변경 금지)은 자르지 말고 원본 비율로")
    source_url: str | None = None
    license_url: str | None = None
    original_url: str | None = None
    title: str | None = None
    width: int | None = None
    height: int | None = None


class Links(BaseModel):
    naver_map_url: str | None = None
    google_place_id: str | None = Field(None, description="영업시간 등은 앱이 Places API로 실시간 조회 (서버는 저장 안 함)")
    kakao_place_id: str | None = None


class DataSource(BaseModel):
    provider: str
    label: str
    license_url: str
    fetched_at: str | None = None
    count: int | None = None
    regions: list[str] = Field(default_factory=list)
    url: str | None = None
    group_counts: dict[str, int] = Field(default_factory=dict)


class ElementSource(BaseModel):
    title: str
    url: str


class PlaceElementProfile(BaseModel):
    elements: list[Element]
    basis: Literal["traditional", "regional", "landscape", "unassigned"]
    label: str
    explanation: str
    sources: list[ElementSource]
    checked_at: str


class PopularitySignal(BaseModel):
    metric: Literal['naver_reviews', 'instagram_place_posts', 'naver_local_rank']
    label: str
    value: int = Field(ge=0)
    source_url: str
    checked_at: date
    scope: str


class DiscoveryEvidence(BaseModel):
    photo_count: int = Field(ge=0)
    popularity: list[PopularitySignal] = Field(default_factory=list)


class PlaceHours(BaseModel):
    provider: Literal['naver', 'official', 'openstreetmap']
    schedule_kind: Literal['regular', 'dated', 'source_text'] = 'regular'
    source_label: str
    source_url: str
    checked_at: date
    stale: bool
    summary: str
    weekly_hours: list[str]
    notes: list[str]
    address: str
    branch_name: str


class ElementPriority(BaseModel):
    element: Element
    label: str
    personal_percent: float = Field(ge=0, le=100)
    personal_points: float = Field(ge=0, le=70)
    day_points: float = Field(ge=0, le=30)
    day_relation: Literal["day_generates_place", "same", "place_generates_day", "place_controls_day", "day_controls_place"]
    day_relation_label: str
    score: float = Field(ge=0, le=100, description="개인 부족 정도와 일진 관계의 합계. 사진 정합도가 아님")
    is_candidate: bool


class RecommendationItem(BaseModel):
    recommendation_id: int
    place_id: str
    place_name: str
    place_group: PlaceGroup = "all"
    spot_name: str
    spot_id: str
    scene_id: str
    time_slot: TimeSlot
    time_slot_label: str
    score: float
    practical_score: float | None
    distance_m: int
    reasons: list[Reason]
    cover_photo: Photo | None = None
    links: Links
    match_basis: Literal["photo", "category", "nearby"] = "photo"
    source: DataSource | None = None
    fit_score: float | None = Field(None, ge=0, le=100, description="입력 프로필과 확인된 사진 특징의 정합도. 평가 근거 또는 입력이 없으면 null")
    recommended_elements: list[Element] = Field(default_factory=list, description="이 장소에서 실제 대응하는 보완 오행·일진 오행")
    saju_match: ElementPriority | None = None
    scoring: ScoreExplanation | None = None
    element_profile: PlaceElementProfile | None = None
    discovery: DiscoveryEvidence | None = None
    hours: PlaceHours | None = None


class DailyContext(BaseModel):
    pillar: str
    day_element: Element
    day_label: str
    personal_element: Element
    personal_label: str
    deficient_elements: list[Element]
    deficient_labels: list[str]
    minimum_percent: float
    target_elements: list[Element] = Field(default_factory=list)
    target_labels: list[str] = Field(default_factory=list)
    element_priorities: list[ElementPriority] = Field(default_factory=list)
    method: str = "personal70_daily30_v1"
    note: str


class RecommendationList(BaseModel):
    visit_date: date
    radius_m: int
    items: list[RecommendationItem]
    missing_inputs: list[str] = Field(description="입력하면 추천이 더 정확해지는 항목")
    daily: DailyContext | None = None
    catalog: DataSource | None = None
    place_group: PlaceGroup = "all"
    score_weights: list[ScoreWeight] = Field(default_factory=list)


class Tip(BaseModel):
    kind: Literal["outfit", "composition", "light"]
    label: str
    text: str


class SceneScore(BaseModel):
    scene_id: str
    spot_id: str
    spot_name: str
    time_slot: TimeSlot
    season: str
    score: float
    passed: bool
    evidence: Literal["photos", "human"] = Field(description="점수의 근거: 사진 분석 또는 사람 확정 (분류 추정은 채점되지 않음)")
    photo_count: int | None = None
    confidence: float | None = None
    reasons: list[Reason]
    recommended_elements: list[Element] = Field(default_factory=list)
    scoring: ScoreExplanation | None = None


class PlaceDetail(BaseModel):
    place_id: str
    name: str
    category: str
    place_group: PlaceGroup = "all"
    address: str | None
    best_scene: SceneScore | None
    other_scenes: list[SceneScore]
    tips: list[Tip]
    visit_notes: list[str]
    open_on_visit_date: bool | None
    photos: list[Photo]
    links: Links
    analysis_pending: bool = Field(False, description="사진 분석 전이라 아직 점수를 낼 수 없는 장소")
    match_basis: Literal["photo", "category", "nearby"] = "photo"
    source: DataSource | None = None
    discovery_reasons: list[Reason] = Field(default_factory=list)
    opening_hours: str | None = None
    fit_score: float | None = Field(None, ge=0, le=100)
    recommended_elements: list[Element] = Field(default_factory=list)
    saju_match: ElementPriority | None = None
    scoring: ScoreExplanation | None = None
    score_weights: list[ScoreWeight] = Field(default_factory=list)
    element_profile: PlaceElementProfile | None = None
    discovery: DiscoveryEvidence | None = None
    hours: PlaceHours | None = None


class FeedbackIn(BaseModel):
    visited: bool | None = None
    rating: int | None = Field(None, ge=1, le=5)
    photo_id: UUID | None = None
    tag_corrections: dict[str, str] | None = Field(
        None, description='실제와 달랐던 태그. 예: {"lighting": "warm_artificial"}')


class PhotoAccepted(BaseModel):
    photo_id: str
    job_queued: bool
    taken_at: str | None


class Bookmark(BaseModel):
    place_id: str
    name: str
    address: str | None = None
    cover_photo: Photo | None = None


# --- 자가진단 -----------------------------------------------------------------
class DiagnosisQuestion(BaseModel):
    id: int
    text: str
    options: list[str]


class DiagnosisIn(BaseModel):
    answers: list[int] = Field(..., max_length=10, description="각 질문에서 고른 선택지 번호(0부터)")


class DiagnosisOut(BaseModel):
    result: str
    result_label: str
    confidence: Literal["high", "medium", "low"]
    second: str | None = None
    second_label: str | None = None
    note: str


# --- 검수 -------------------------------------------------------------------
class ReviewItem(BaseModel):
    scene_id: str
    place_name: str
    spot_name: str
    time_slot: str
    season: str
    confidence: float | None
    photo_count: int | None
    reasons: list[str]


class SceneEdit(BaseModel):
    color_temp: Literal["warm", "neutral", "cool"] | None = None
    brightness: Literal["bright_soft", "mid", "high_contrast"] | None = None
    saturation: Literal["muted", "mid", "vivid"] | None = None
    lighting: Literal["diffused_natural", "direct_golden", "warm_artificial", "cool_artificial_night"] | None = None
    form: Literal["linear", "curved", "organic"] | None = None
    texture: Literal["sleek", "soft", "rough"] | None = None
    scale: Literal["compact", "medium", "spacious"] | None = None
    crowd_level: Literal["quiet", "moderate", "busy"] | None = None
    place_character: Literal["detail", "concept"] | None = None
    photo_mood: Literal["structural", "emotional"] | None = None
    elements: list[Element] | None = None
    verify: bool = Field(True, description="true면 검수 완료로 확정 (이후 자동 태깅이 덮어쓰지 않음)")
