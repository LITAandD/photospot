"""Public places ranked by observed photo attributes and sourced interpretations."""
import json
import re
import unicodedata
from . import services as svc, labels as L, schemas as S
from pipeline import place_catalog as catalog
from pipeline.place_categories import CATEGORIES, group_for
from pipeline.place_quality import recommendation_exclusion
from .score_display import weight_guide
from .catalog_scoring import WEIGHTS, explanation
from pipeline.catalog_visuals import evidence_for
from .catalog_media import cover_thumbnail, photos_for
from . import photo_likes
from .scoring_cache import NearbyIndex, elements_for, memo, place_elements
from pipeline.catalog_instagram import posts_for
from pipeline.cafe_popularity import popularity_for, popularity_score
from pipeline.place_hours import hours_for
from pipeline.catalog_visitors import rankings as visitor_rankings
from pipeline.catalog_mbti import descriptions_for
from pipeline.cafe_photos import display_name
from pipeline.dining_curation import evidence as dining_evidence

# 입력하면 정합도 평가에 쓰이는 항목(키·J/P는 장소 점수에 쓰지 않는다).
MISSING_INPUTS = [('pc_season', '퍼스널컬러'), ('body_type', '체형'), ('mbti', 'MBTI')]
CORPORATE = re.compile(r'\(주\)|㈜|주식회사|\(사\)|\(재\)|사단법인|재단법인|\(유\)|유한회사')
HANGUL = re.compile(r'[가-힣]')
# 하천·숲길·산처럼 여러 지점으로 등록되는 지형은 같은 이름이면 1km까지 한 장소로 본다.
LINEAR = re.compile(r'(?:천|천변|하천|수로|숲길|둘레길|산책로|산책길|올레길|자락길|해안길|해변길|강변|공원|산|봉|길|해수욕장|해변)$')
CLOSED = re.compile(r'휴무|휴궁|휴관|휴점|휴장|휴원|closed', re.I)


def public_name(place):
    """표시용 장소명. 법인 표기·영문 괄호 병기·'A / B' 중복 표기를 정리하고 한글명이 있으면 한글을 우선한다. 장소마다 한 번만 계산한다."""
    if not place.get('id'): return _public_name(place)
    return memo('public_name', (place['id'], place.get('name')), lambda: _public_name(place))


def _public_name(place):
    raw = display_name(place)
    name = CORPORATE.sub(' ', unicodedata.normalize('NFKC', raw))
    korean_alias = re.fullmatch(r'\s*([^()]*)\(([^()]*)\)\s*', name)
    if korean_alias and HANGUL.search(korean_alias.group(2)) and not HANGUL.search(korean_alias.group(1)):
        name = korean_alias.group(2)                                   # GAMDO(감도) → 감도
    def paren(match):
        inner = match.group(1).strip()
        outer = (name[:match.start()] + name[match.end():]).strip()
        if not HANGUL.search(inner) or inner in outer: return ' '   # ( Korea Furniture Museum), (521)
        return f' {inner} '                                        # 프리츠(양재점) → 프리츠 양재점
    name = re.sub(r'\s*\(([^()]*)\)', paren, name)
    if not HANGUL.search(name):
        name = next((m.group(1) for m in re.finditer(r'\(([^()]*)\)', raw) if HANGUL.search(m.group(1))), name)
    parts = [p for p in re.split(r'\s+/\s+|\s*／\s*|\s+\|\s+', name) if p.strip()]
    name = next((p for p in parts if HANGUL.search(p)), parts[0] if parts else name)
    name = ' '.join(name.split()).strip(' -·,')
    return name or raw


def closed_on_visit(hours):
    """촬영일이 확인된 휴무일인지. 원문 보존(source_text)·만료(stale) 일정은 단정하지 않는다."""
    return bool(hours and not hours['stale'] and hours.get('schedule_kind', 'regular') != 'source_text'
                and CLOSED.search(hours['summary']))


def affinities(place, profile, daily):
    kind = place["category"]
    reasons = []
    def add(label, weight): reasons.append({"label": label, "points": weight, "layer": "auxiliary"})
    if daily:
        match = svc.saju_place_match(place_elements(place), daily)
        if match:
            if match['personal_points']:
                add(f"부족한 {match['label']} 보완 · 내 비율 {match['personal_percent']:g}%", match['personal_points'])
            add(match['day_relation_label'], match['day_points'])
    return reasons


def unique_places(entries, photos=None):
    """Collapse duplicate representations of one place, keeping the best-ranked entry.

    Same-named places merge within 150m, or within 1km for linear features (rivers,
    trails, mountains, parks). A shared wikidata id or an identical public gallery is
    the same place only within 150m: OSM tags every sub-park of 월드컵공원 with the
    umbrella id and they share one gallery, yet 하늘공원·난지천공원·난지한강공원 are
    distinct parks 1-2km apart. Prefix names (KB아트홀·KB아트홀 강남) merge only when the
    pair is the same kind of place or at most one of them is photographed, so 남산 stays
    apart from 남산서울타워. Different branches remain separate and source records with
    their detail/bookmark URLs stay intact.
    """
    photos = photos or {}
    index, seen_keys = NearbyIndex(), {}
    for entry in entries:
        place = entry[0]
        tags = place.get('tags') or {}
        if isinstance(tags, str): tags = json.loads(tags)
        group, count = group_for(place['category']), len(photos.get(place['id'], []))
        keys = [('wikidata', tags['wikidata'])] if tags.get('wikidata') else []
        if count >= 2:  # 한 장짜리 범용 사진은 서로 다른 장소가 공유할 수 있다.
            keys.append(('gallery', tuple(sorted(p['url'] for p in photos[place['id']]))))
        # 같은 wikidata·갤러리라도 150m 밖이면 다른 장소다(월드컵공원의 하위 공원들, 청계천·청계천공원).
        if any(other_group == group and catalog.distance_m(other['lat'], other['lng'], place) <= 150
               for key in keys for other_group, other in seen_keys.get(key, ())):
            continue
        name = ''.join(unicodedata.normalize('NFKC', public_name(place)).split()).casefold()
        reach = 1000 if place['category'] in {'waterfront', 'scenic'} or LINEAR.search(place['name'].strip()) else 150
        # 'KB아트홀'·'KB아트홀 강남'처럼 한쪽 이름이 다른 쪽의 접두사인 인접 등록도 같은 장소로 본다.
        # 단 종류가 다르고 둘 다 사진이 있으면 별개다(남산·남산서울타워, 탑골공원·탑골공원 팔각정).
        if any((other_name == name or (len(min(name, other_name, key=len)) >= 2 and
                (name.startswith(other_name) or other_name.startswith(name)) and
                (other['category'] == place['category'] or not count or not photos.get(other['id']))))
               and catalog.distance_m(other['lat'], other['lng'], place) <= (reach if other_name == name else 150)
               for other_name, other in index.near(group, place, reach)):
            continue
        index.add(group, name, place)
        for key in keys: seen_keys.setdefault(key, []).append((group, place))
        yield entry


def recommend(body, card, nearby=True, *, detail_ids=None, gallery_ids=None, voter=None):
    """nearby=False scores only body.place_ids (place detail); each place's result is independent of the others."""
    info = catalog.metadata()
    if not info["count"]:
        from fastapi import HTTPException
        raise HTTPException(503, "추천할 장소를 준비하고 있어요. 잠시 후 다시 확인해 주세요.")
    profile = body.profile.model_dump()
    guide = [w for w in weight_guide(WEIGHTS) if not w['optional']]
    daily = svc.daily_context(body.visit_date, body.element, body.use_saju, body.percents)
    requested = set(body.place_ids)
    def eligible(place):
        pid = place['id']
        return (place['active'] and place['distance_m'] <= body.radius_m and
                (pid not in excluded or pid in requested) and
                (not photo_only or bool(counts.get(pid))) and
                (not min_fit or (scores[pid]['score'] is not None and scores[pid]['score'] >= min_fit)) and
                (body.place_group == 'all' or group_for(place['category']) == body.place_group) and
                (not daily or (matches[pid] is not None and scores[pid]['score'] != 0)))
    # Plus filters exist only on the authenticated query; the public preview has none.
    photo_only, min_fit = getattr(body, 'photo_only', False), getattr(body, 'min_fit', 0)
    rows = catalog.search(body.lat, body.lng, body.radius_m, body.place_ids, nearby=nearby)
    # Rank the complete eligible set before taking 30; otherwise photographed
    # places beyond the old distance cutoff would never be discovered.
    photos = photos_for(p['id'] for p in rows)
    # 큐레이션 대표사진은 표를 받아도 그대로일 수 있으므로, 정렬 뒤 대표사진이 바뀌었는지로 선택 근거를 적는다.
    curated = {pid: photo_likes.photo_id(ps[0]) for pid, ps in photos.items() if ps}
    votes, likes_enabled = photo_likes.snapshot(photos, voter)
    photos = photo_likes.rank(photos, votes, likes_enabled)
    for ps in photos.values():                 # 목록 카드용 320px 썸네일(rank()가 돌려준 사본이라 캐시는 그대로)
        for p in ps: p['thumb_url'] = cover_thumbnail(p)
    counts = {pid: len(ps) for pid, ps in photos.items()}
    curation = {p['id']: dining_evidence(p) for p in rows}
    # 사진 또는 큐레이션·편집 근거는 정합도·평가 수가 같은 경우의 보조 기준. 지도 노드만 있는 동네 시설·체인 매장은 목록에서 뺀다.
    content = {p['id']: bool(counts.get(p['id'])) or bool(curation[p['id']]) or elements_for(p)['basis'] == 'traditional' for p in rows}
    excluded = {p['id'] for p in rows if recommendation_exclusion(p, photographed=bool(counts.get(p['id'])), curated=bool(curation[p['id']]))}
    popularity = popularity_for(p['id'] for p in rows if group_for(p['category']) == 'cafe')
    evidence = evidence_for(photos, selected_photos=photos)
    covers = {pid: ps[0] for pid, ps in photos.items() if ps}
    evidence.update(photo_likes.evidence_for(covers))
    visitor_context, visitors = visitor_rankings()
    descriptions = descriptions_for(p['id'] for p in rows)
    scores = {p['id']: explanation(profile, evidence.get(p['id']), p, visitors.get(p['id'], visitor_context), descriptions.get(p['id'])) for p in rows}
    for pid, cover in covers.items():
        scores[pid].update(evidence_photo_id=cover['photo_id'], evidence_photo_url=cover['url'],
                           photo_analysis_pending=pid not in evidence,
                           photo_selection='likes' if cover['photo_id'] != curated[pid] else 'curated')
    matches = {p['id']: svc.saju_place_match(place_elements(p), daily) for p in rows}
    hours_by_id = {p['id']: hours_for(p, body.visit_date) for p in rows}
    for hours in hours_by_id.values():
        if hours: hours['closed'] = closed_on_visit(hours)
    ranked = []
    for p in rows:
        reasons = affinities(p, profile, daily)
        ranked.append((p, reasons, sum(r["points"] for r in reasons)))
    def ranking_key(entry):
        place, _, affinity = entry
        pid = place['id']
        scoring = scores[pid]
        # The displayed total fit is always the primary key, including explicitly
        # labelled category estimates. Unknown is below a measured zero. Coverage,
        # photos/curation and opening hours only break ties; none can overtake fit.
        fit_score = scoring['score'] if scoring['score'] is not None else -1
        evaluated = sum(m['status'] == 'scored' for m in scoring['metrics'])
        hours = hours_by_id[pid]
        return (-fit_score, -evaluated, not content[pid], bool(hours and hours['closed']), -bool(counts.get(pid)),
                -(matches[pid]['score'] if matches[pid] else -1) if daily else 0,
                -affinity, -popularity_score(popularity.get(pid, [])), place['distance_m'], pid)

    ranked.sort(key=ranking_key)
    limit = getattr(body, 'limit', 30)
    recommended = list(unique_places((entry for entry in ranked if eligible(entry[0])), photos))[:limit]
    recommended_ids = {p['id'] for p, _, _ in recommended}
    selected = set(recommended_ids)
    selected.update(body.place_ids)
    instagram = posts_for(selected)
    items, places = [], {}
    for place, reasons, rank in ranked:
        if place["id"] not in selected: continue
        pid, kind = place["id"], CATEGORIES[place["category"]]
        hours = hours_by_id[pid]
        signals = popularity.get(pid, [])
        discovery = {'photo_count': counts.get(pid, 0), 'popularity': signals, 'curation': curation[pid]}
        links = {'naver_map_url': next((s['source_url'] for s in signals if s['metric'] == 'naver_reviews'), None)}
        group = group_for(place["category"])
        source = {"provider": "openstreetmap", "label": catalog.SOURCE_LABEL, "license_url": catalog.LICENSE_URL,
                  "url": place["source_url"], "fetched_at": place["fetched_at"]}
        scoring = scores[pid]
        fit = scoring['score']
        name = public_name(place)
        # Display the same observed contributions that produced the score.
        reasons = [{'label': m['label'] + ' · ' + m['note'].removeprefix('사진에서 확인: '),
                    'points': m['points'], 'layer': 'auxiliary' if m['key'].startswith('mbti') else 'practical'} for m in scoring['metrics']
                   if m['status'] == 'scored' and m['points'] > 0]
        if daily:
            reasons.extend({**r, 'points': 0} for r in affinities(place, {}, daily))
        elements = svc.recommended_elements(place_elements(place), daily)
        basis = scoring['basis'] if fit is not None else 'nearby'
        notes = ["촬영 가능 구역과 이용 조건을 확인해 주세요." if hours else "방문 전 영업시간과 촬영 가능 여부를 지도 또는 공식 안내에서 확인해 주세요."]
        if hours and hours['closed']: notes.insert(0, "촬영일이 확인된 휴무일이에요. 다른 날짜를 고르거나 현장 안내를 확인해 주세요.")
        if not place["active"]: notes.insert(0, "최근 운영 여부를 확인하지 못한 장소예요. 방문 전 확인해 주세요.")
        notes.append(f"지도 좌표: {place['lat']:.6f}, {place['lng']:.6f}")
        if group == "festival":
            notes.insert(0, "축제장·공연장·전시 공간으로 등록된 장소예요. 촬영일의 실제 행사 개최 여부·일정·입장 조건은 확인이 필요해요.")
        tips = []
        if profile.get("pc_season"):
            tips.append({"kind": "outfit", "label": "프로필 코디 참고", "text": svc.OUTFIT[profile["pc_season"]] + ". 실제 장소의 빛·색은 현장에서 확인해 주세요."})
        places[pid] = {"place_id": pid, "name": name, "category": kind, "address": (hours['address'] or place["address"]) if hours else place["address"],
            "place_group": group,
            "best_scene": None, "other_scenes": [], "tips": tips, "visit_notes": notes, "open_on_visit_date": None,
            "photos": photos.get(pid, []) if gallery_ids is None or pid in gallery_ids else photos.get(pid, [])[:1], "instagram_posts": instagram.get(pid, []), "links": links, "analysis_pending": fit is None, "match_basis": basis, "source": source,
            "discovery_reasons": reasons, "opening_hours": place["opening_hours"],
            "fit_score": fit, "recommended_elements": elements, "saju_match": matches[pid], "scoring": scoring, "score_weights": guide,
            "element_profile": elements_for(place), "discovery": discovery, "hours": hours}
        if detail_ids is not None and pid not in detail_ids:
            del places[pid]
        if pid not in recommended_ids: continue
        # ID is the persistent catalog row identifier, not an invented scored scene.
        # Unknown hours are a neutral pointer to the map, never a '미확인' verdict.
        items.append({"recommendation_id": place["row_id"], "place_id": pid, "place_name": name,
            "place_group": group,
            "spot_id": "", "scene_id": "", "spot_name": kind, "time_slot": body.time_slot or "midday",
            "time_slot_label": "행사 일정 확인 필요" if group == "festival" else hours['summary'] if hours else "운영시간 · 지도에서 확인", "score": fit if fit is not None else 0, "practical_score": None,
            "distance_m": place["distance_m"], "reasons": reasons, "links": links, "match_basis": basis, "source": source,
            "cover_photo": next(iter(photos.get(pid, [])), None),
            "instagram_post_count": len(instagram.get(pid, [])),
            "fit_score": fit, "recommended_elements": elements, "saju_match": matches[pid], "scoring": scoring,
            "element_profile": elements_for(place), "discovery": discovery, "hours": hours})
    rec = {"visit_date": body.visit_date, "radius_m": body.radius_m, "items": items, "daily": daily, "catalog": info,
           "missing_inputs": [label for key, label in MISSING_INPUTS if not profile.get(key)],
           "place_group": body.place_group, "score_weights": guide}
    return {"card": card, "recommendations": S.RecommendationList.model_validate(rec),
            "places": {k: S.PlaceDetail.model_validate(v) for k, v in places.items()}}
