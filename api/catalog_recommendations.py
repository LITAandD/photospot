"""Public places ranked by observed photo attributes and sourced interpretations."""
from . import services as svc, labels as L, schemas as S
from pipeline import place_catalog as catalog
from pipeline.place_categories import CATEGORIES, group_for
from .score_display import weight_guide
from .catalog_scoring import WEIGHTS, explanation
from pipeline.catalog_visuals import evidence_for
from pipeline.catalog_photos import photos_for, photo_counts_for
from pipeline.cafe_popularity import popularity_for, popularity_score
from pipeline.place_editorial import resolve_elements
from pipeline.place_hours import hours_for
from pipeline.catalog_visitors import rankings as visitor_rankings
from pipeline.cafe_photos import display_name
from pipeline.dining_curation import evidence as dining_evidence


def place_elements(place):
    return set(resolve_elements(place)['elements'])


def affinities(place, profile, daily):
    kind = place["category"]
    reasons = []
    def add(label, weight): reasons.append({"label": label, "points": weight, "layer": "auxiliary"})
    mbti = profile.get("mbti") or ""
    if len(mbti) == 4:
        if mbti[2] == "T" and kind in {"museum", "gallery", "heritage", "cultural_venue", "event_venue"}: add("T 성향 선택 · 문화·건축 유형 탐색", 2)
        if mbti[2] == "F" and kind in {"park", "viewpoint", "waterfront", "scenic"}: add("F 성향 선택 · 자연·전망 유형 탐색", 2)
    if daily:
        match = svc.saju_place_match(place_elements(place), daily)
        if match:
            if match['personal_points']:
                add(f"부족한 {match['label']} 보완 · 내 비율 {match['personal_percent']:g}%", match['personal_points'])
            add(match['day_relation_label'], match['day_points'])
    return reasons


def recommend(body, card):
    info = catalog.metadata()
    if not info["count"]:
        from fastapi import HTTPException
        raise HTTPException(503, "추천할 장소를 준비하고 있어요. 잠시 후 다시 확인해 주세요.")
    profile = body.profile.model_dump()
    guide = [w for w in weight_guide(WEIGHTS) if not w['optional']]
    daily = svc.daily_context(body.visit_date, body.element, body.use_saju, body.percents)
    def eligible(place):
        return (place['active'] and place['distance_m'] <= body.radius_m and
                (not body.photo_only or bool(counts.get(place['id']))) and
                (not body.min_fit or (scores[place['id']]['score'] is not None and scores[place['id']]['score'] >= body.min_fit)) and
                (body.place_group == 'all' or group_for(place['category']) == body.place_group) and
                (not daily or matches[place['id']] is not None))
    rows = catalog.search(body.lat, body.lng, body.radius_m, body.place_ids)
    # Rank the complete eligible set before taking 30; otherwise photographed
    # places beyond the old distance cutoff would never be discovered.
    counts = photo_counts_for(p['id'] for p in rows)
    popularity = popularity_for(p['id'] for p in rows if group_for(p['category']) == 'cafe')
    evidence = evidence_for(p['id'] for p in rows if counts.get(p['id']))
    visitor_context, visitors = visitor_rankings()
    scores = {p['id']: explanation(profile, evidence.get(p['id']), p, visitors.get(p['id'], visitor_context)) for p in rows}
    matches = {p['id']: svc.saju_place_match(place_elements(p), daily) for p in rows}
    ranked = []
    for p in rows:
        reasons = affinities(p, profile, daily)
        ranked.append((p, reasons, sum(r["points"] for r in reasons)))
    def ranking_key(entry):
        place, _, affinity = entry
        pid = place['id']
        scoring = scores[pid]
        # Count completed evaluations, including zero/negative matches. Missing
        # inputs and evidence do not count, regardless of their possible weight.
        evaluated = sum(m['status'] == 'scored' for m in scoring['metrics'])
        return (-evaluated, -(scoring['score'] if scoring['score'] is not None else -1),
                -(matches[pid]['score'] if matches[pid] else -1) if daily else 0,
                -bool(counts.get(pid)), -affinity,
                -popularity_score(popularity.get(pid, [])), place['distance_m'], pid)

    ranked.sort(key=ranking_key)
    limit = getattr(body, 'limit', 30)
    selected = {p["id"] for p, _, _ in [entry for entry in ranked if eligible(entry[0])][:limit]}
    selected.update(body.place_ids)
    photos = photos_for(selected)
    items, places = [], {}
    for place, reasons, rank in ranked:
        if place["id"] not in selected: continue
        pid, kind = place["id"], CATEGORIES[place["category"]]
        hours = hours_for(place, body.visit_date)
        signals = popularity.get(pid, [])
        discovery = {'photo_count': counts.get(pid, 0), 'popularity': signals, 'curation': dining_evidence(place)}
        links = {'naver_map_url': next((s['source_url'] for s in signals if s['metric'] == 'naver_reviews'), None)}
        group = group_for(place["category"])
        source = {"provider": "openstreetmap", "label": catalog.SOURCE_LABEL, "license_url": catalog.LICENSE_URL,
                  "url": place["source_url"], "fetched_at": place["fetched_at"]}
        scoring = scores[pid]
        fit = scoring['score']
        # Display the same observed contributions that produced the score.
        reasons = [{'label': m['label'] + ' · ' + m['note'].removeprefix('사진에서 확인: '),
                    'points': m['points'], 'layer': 'auxiliary' if m['key'].startswith('mbti') else 'practical'} for m in scoring['metrics']
                   if m['status'] == 'scored' and m['points'] > 0]
        if daily:
            reasons.extend({**r, 'points': 0} for r in affinities(place, {}, daily))
        elements = svc.recommended_elements(place_elements(place), daily)
        basis = 'photo' if fit is not None else 'nearby'
        notes = ["촬영 가능 구역과 이용 조건을 확인해 주세요." if hours else "방문 전 영업시간과 촬영 가능 여부를 지도 또는 공식 안내에서 확인해 주세요."]
        if not place["active"]: notes.insert(0, "최근 운영 여부를 확인하지 못한 장소예요. 방문 전 확인해 주세요.")
        notes.append(f"지도 좌표: {place['lat']:.6f}, {place['lng']:.6f}")
        if group == "festival":
            notes.insert(0, "축제장·공연장·전시 공간으로 등록된 장소예요. 촬영일의 실제 행사 개최 여부·일정·입장 조건은 확인이 필요해요.")
        tips = []
        if profile.get("pc_season"):
            tips.append({"kind": "outfit", "label": "프로필 코디 참고", "text": svc.OUTFIT[profile["pc_season"]] + ". 실제 장소의 빛·색은 현장에서 확인해 주세요."})
        places[pid] = {"place_id": pid, "name": display_name(place), "category": kind, "address": (hours['address'] or place["address"]) if hours else place["address"],
            "place_group": group,
            "best_scene": None, "other_scenes": [], "tips": tips, "visit_notes": notes, "open_on_visit_date": None,
            "photos": photos.get(pid, []), "links": links, "analysis_pending": fit is None, "match_basis": basis, "source": source,
            "discovery_reasons": reasons, "opening_hours": place["opening_hours"],
            "fit_score": fit, "recommended_elements": elements, "saju_match": matches[pid], "scoring": scoring, "score_weights": guide,
            "element_profile": resolve_elements(place), "discovery": discovery, "hours": hours}
        if len(items) >= limit or not eligible(place): continue
        # ID is the persistent catalog row identifier, not an invented scored scene.
        items.append({"recommendation_id": place["row_id"], "place_id": pid, "place_name": display_name(place),
            "place_group": group,
            "spot_id": "", "scene_id": "", "spot_name": kind, "time_slot": body.time_slot or "midday",
            "time_slot_label": "행사 일정 확인 필요" if group == "festival" else hours['summary'] if hours else "운영시간 · 지도에서 확인" if group == "travel" else "영업시간 미확인", "score": fit if fit is not None else 0, "practical_score": None,
            "distance_m": place["distance_m"], "reasons": reasons, "links": links, "match_basis": basis, "source": source,
            "cover_photo": next(iter(photos.get(pid, [])), None),
            "fit_score": fit, "recommended_elements": elements, "saju_match": matches[pid], "scoring": scoring,
            "element_profile": resolve_elements(place), "discovery": discovery, "hours": hours})
    rec = {"visit_date": body.visit_date, "radius_m": body.radius_m, "items": items, "daily": daily, "catalog": info,
           "missing_inputs": [], "place_group": body.place_group, "score_weights": guide}
    return {"card": card, "recommendations": S.RecommendationList.model_validate(rec),
            "places": {k: S.PlaceDetail.model_validate(v) for k, v in places.items()}}
