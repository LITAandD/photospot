"""real_smoke 스크립트를 가짜 TourAPI로 끝까지 돌린다 (진짜 키로는 PC에서 실행)."""
import io
import os
import sys
import urllib.parse
import uuid

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts import real_smoke   # noqa: E402

DSN = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="DATABASE_URL 없음")
RUN = uuid.uuid4().hex[:5]


def fake_json(url):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if "areaBasedList2" in url:
        items = [{"contentid": f"{RUN}{i}", "contenttypeid": "12", "title": f"진짜테스트 {RUN} {i}", "addr1": f"서울특별시 종로구 길 {i}",
                  "areacode": "1", "mapx": f"{126.97 + i * 0.002:.6f}", "mapy": f"{37.57 + i * 0.001:.6f}",
                  "firstimage": f"http://tong.visitkorea.or.kr/{RUN}{i}.jpg", "cpyrhtDivCd": "Type1",
                  "cat1": "A02", "cat2": "A0206", "cat3": "A02060500"} for i in range(6)]
        return {"response": {"body": {"totalCount": 6, "items": {"item": items}}}}
    if "detailImage2" in url:
        cid = q["contentId"][0]
        return {"response": {"body": {"items": {"item": [
            {"originimgurl": f"http://tong.visitkorea.or.kr/{cid}_{k}.jpg", "cpyrhtDivCd": "Type1", "serialnum": str(k)} for k in range(5)]}}}}
    raise AssertionError(url)


def fake_bytes(url):
    buf = io.BytesIO(); Image.new("RGB", (400, 300), (225, 232, 242)).save(buf, format="JPEG"); return buf.getvalue()


def test_real_smoke_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path)); monkeypatch.setenv("TOURAPI_KEY", "fake")
    logs = []
    code = real_smoke.main(["--areas", "1", "--target", "6", "--vision", "off"], http_json=fake_json, http_get=fake_bytes, log=logs.append)
    text = "\n".join(logs)
    assert code == 0, text
    assert "채점 가능한 장소" in text and "장면 6개 집계" in text          # 사진 6장(대표1+상세5)씩 분석됨
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), min(photo_count), bool_and(scorable) FROM scene_integrity WHERE place_name LIKE %s AND evidence='photos'", (f"진짜테스트 {RUN} %",))
        n, minp, all_scorable = cur.fetchone()
        assert n == 6 and minp == 6 and all_scorable
