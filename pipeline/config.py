"""파이프라인 설정값. 수동 검수된 장면 데이터로 주기적으로 보정(calibration)한다."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ColorThresholds:
    # 웜/쿨: warmth 지수 (중성색 표면의 색 편향 60% + 배경 전체 색 40%, 식물 초록은 제외)
    warm_min: float = 10.0
    cool_max: float = 3.0
    # 명도·대비 (CIELAB L*, 0~100)
    bright_l_min: float = 62.0
    bright_std_max: float = 22.0
    contrast_std_min: float = 27.0
    contrast_range_min: float = 75.0      # p95 - p5
    # 채도 (보이는 픽셀의 평균 C*)
    muted_c_max: float = 15.0
    vivid_c_min: float = 38.0
    # 야간 판정 (조명 규칙 보조용)
    night_l_median_max: float = 28.0
    night_range_min: float = 50.0


@dataclass(frozen=True)
class PipelineConfig:
    vision_model: str = "claude-haiku-4-5-20251001"   # 대량 태깅용. 어려운 장면은 상위 모델로 재분석
    vision_max_side: int = 1024                        # API 전송 전 리사이즈
    analysis_max_side: int = 384                       # 색 분석용 리사이즈
    palette_k: int = 5
    min_background_ratio: float = 0.15                 # 인물 제외 후 배경이 이보다 적으면 색 신뢰도 하향
    min_photos_full_confidence: int = 5                # 사진이 이보다 적으면 장면 신뢰도 감쇠
    review_confidence: float = 0.6                     # 이 값 미만이면 검수 대기열로
    element_vision_share: float = 0.4                  # 오행: AI가 이 비율 이상 사진에서 봤으면 채택
    element_palette_share: float = 0.6                 # 오행: 색 팔레트 근거만 있을 땐 더 높은 비율 요구
    colors: ColorThresholds = field(default_factory=ColorThresholds)


# 출처별 신뢰 가중치 (직접 촬영 > 공공 사진 > 사장님 > 사용자)
SOURCE_WEIGHT = {"own_shoot": 1.0, "tourapi": 0.9, "owner_upload": 0.8, "user_upload": 0.7}

# 서울 기준 월별 일출·일몰 근사값 (KST). 지역별 오차 ±20분 수준
SUN_TIMES = {
    1: ("07:45", "17:40"), 2: ("07:25", "18:10"), 3: ("06:50", "18:40"),
    4: ("06:05", "19:05"), 5: ("05:30", "19:30"), 6: ("05:10", "19:55"),
    7: ("05:20", "19:55"), 8: ("05:45", "19:30"), 9: ("06:10", "18:50"),
    10: ("06:35", "18:10"), 11: ("07:05", "17:30"), 12: ("07:35", "17:20"),
}
