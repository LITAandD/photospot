"""enum 값 → 화면에 보여줄 한국어 라벨. 앱과 서버가 같은 문구를 쓰도록 서버에서 내려준다."""

VALUE_LABELS = {
    "lighting":        {"diffused_natural": "부드러운 자연광", "direct_golden": "골든아워 햇빛",
                        "warm_artificial": "따뜻한 조명", "cool_artificial_night": "차가운 조명·야경"},
    "color_temp":      {"warm": "웜톤 배경", "neutral": "뉴트럴 배경", "cool": "쿨톤 배경"},
    "brightness":      {"bright_soft": "밝고 부드러운 명도", "mid": "중간 명도", "high_contrast": "선명한 대비"},
    "saturation":      {"muted": "차분한 채도", "mid": "중간 채도", "vivid": "선명한 색감"},
    "form":            {"linear": "직선 중심", "curved": "곡선 중심", "organic": "자연스러운 공간", "volumetric": "큰 형체 중심"},
    "setting":         {"indoor": "실내 이용 공간", "outdoor": "야외 공간", "mixed": "실내·야외 함께 이용"},
    "texture":         {"sleek": "매끈한 질감", "soft": "부드러운 질감", "rough": "거친 자연 소재"},
    "scale":           {"compact": "아늑한 공간", "medium": "적당한 공간", "spacious": "넓은 공간"},
    "crowd_level":     {"quiet": "한적함", "moderate": "적당한 인파", "busy": "활기참"},
    "place_character": {"detail": "디테일 맛집", "concept": "컨셉 공간"},
    "photo_mood":      {"structural": "건축·구도", "emotional": "감성 분위기"},
    "element":         {"wood": "목(木) 기운", "fire": "화(火) 기운", "earth": "토(土) 기운",
                        "metal": "금(金) 기운", "water": "수(水) 기운"},
}
SEASON = {"spring_warm": "봄 웜", "summer_cool": "여름 쿨", "autumn_warm": "가을 웜", "winter_cool": "겨울 쿨"}
SUBTONE = {"light": "라이트", "bright": "브라이트", "true": "트루", "mute": "뮤트", "deep": "딥"}
BODY = {"straight": "스트레이트", "wave": "웨이브", "natural": "내추럴"}
TIME_SLOT = {"morning": "아침", "midday": "낮", "golden_hour": "골든아워", "night": "밤"}
ELEMENT_PLACE = {"wood": "숲·식물이 있는 곳", "fire": "노을·불빛이 있는 곳", "earth": "흙·도자기·황토 공간",
                 "metal": "석조·금속 건축", "water": "물가"}
ELEMENT_PREFIX = {"wood": "숲을 닮은", "fire": "노을빛 머금은", "earth": "흙내음 품은",
                  "metal": "은빛 머금은", "water": "물빛 머금은"}
WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"]
