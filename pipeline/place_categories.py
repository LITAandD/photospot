"""Shared catalog categories; a venue classification does not imply an event date."""

CATEGORIES = {
    "cafe": "카페", "museum": "박물관·미술관", "gallery": "갤러리", "waterfront": "물가·해변",
    "park": "공원·정원", "viewpoint": "전망 명소", "heritage": "역사 명소", "attraction": "관광 명소",
    "scenic": "산·자연 명소", "theme_park": "테마파크", "festival_site": "축제장",
    "event_venue": "전시·컨벤션 공간", "cultural_venue": "공연·문화 공간",
}
GROUPS = {
    "cafe": {"cafe"},
    "travel": {"museum", "gallery", "waterfront", "park", "viewpoint", "heritage", "attraction", "scenic", "theme_park", "street"},
    "festival": {"festival_site", "event_venue", "cultural_venue"},
}


def group_for(category):
    return next((key for key, values in GROUPS.items() if category in values), "all")
